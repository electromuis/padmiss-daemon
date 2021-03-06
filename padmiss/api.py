#!/usr/bin/env python

import requests
import json
import logging
import socket
from graphqlclient import GraphQLClient

log = logging.getLogger(__name__)

class Base(object):
    __repr_suppress__ = set()

    def __init__(self, **kwargs):
        for k, c in self.__fields__.items():
            if not k in kwargs:
                if c == None:
                    raise TournamentApiError('Required parameter \'%s\' missing' % k)
                else:
                    val = c
            else:
                val = kwargs[k]
            if c and isinstance(val, dict):
                val = c(**val)
            setattr(self, k, val)

    def __repr__(self):
        return '(%s %s)' % (
            type(self).__name__,
            ' '.join('%s=%s' % (k, repr(v)) for k, v in self.__dict__.items() if not k in self.__repr_suppress__)
        )


class FlattenedBase(Base):
    pass


class Player(FlattenedBase):
    __fields__ = {
        'nickname': None,
        'shortNickname': '',
		'avatarIconUrl': '',
        'rfidUid': '',
        '_id': None,
        'metaData': "{}",
        'mountType': False
    }

    def getMeta(self, field):
        if self.metaData == None:
            return None

        data = json.loads(self.metaData)
        if field in data:
            return data[field]

        return None


class ScoreBreakdown(FlattenedBase):
    __fields__ = {
        'fantastics': None,
        'excellents': None,
        'greats': None,
        'decents': None,
        'wayoffs': None,
        'misses': None,
        'holds': None,
        'holdsTotal': None,
        'minesHit': None,
        'minesAvoided': None,
        'minesTotal': None,
        'rolls': None,
        'rollsTotal': None,
        'jumps': None,
        'jumpsTotal': None,
        'hands': None,
        'handsTotal': None
    }


class Score(FlattenedBase):
    __fields__ = {
        'scoreBreakdown': ScoreBreakdown,
        'scoreValue': None,
        'passed': None,
        'secondsSurvived': None
    }


class Song(FlattenedBase):
    __fields__ = {
        'title': None,
        'titleTransliteration': None,
        'subTitle': None,
        'subTitleTransliteration': None,
        'artist': None,
        'artistTransliteration': None,
        'durationSeconds': None
    }


class TimingWindows(Base):
    __fields__ = {
        'fantasticTimingWindow': None,
        'excellentTimingWindow': None,
        'greatTimingWindow': None,
        'decentTimingWindow': None,
        'wayoffTimingWindow': None,
        'mineTimingWindow': None,
        'holdTimingWindow': None,
        'rollTimingWindow': None
    }


class ChartUpload(Base):
    __repr_suppress__ = set(('stepData',))

    __fields__ = {
        'hash': None,
        'meter': None,
        'playMode': None,
        'stepData': None,
        'stepArtist': None,
        'song': Song,
        'score': Score,
        'group': None,
        'cabSide': None,
        'speedMod': None,
        'musicRate': None,
        'modsTurn': None,
        'modsTransform': None,
        'modsOther': None,
        'noteSkin': None,
        'perspective': None,
        'timingWindows': TimingWindows,
        'inputEvents': [],
        'noteScoresWithBeats': []
    }

class InputEvent(Base):
    __fields__ = {
        'beat': None,
        'column': None,
        'released': None
    }

class NoteScore(Base):
    __fields__ = {
        'beat': None,
        'column': None,
        'holdNoteScore': None,
        'tapNoteScore': None,
        'offset': None
    }

class TournamentApiError(Exception):
    pass


class TournamentApi(object):
    def __init__(self, config):
        if isinstance(config, str):
            self.url = config
        else:
            self.url = config.padmiss_api_url
            self.key = config.api_key

        self.config = config
        self.graph = GraphQLClient(self.url + '/graphiql')
        self.auth = None

    def authenticate(self, username, password):
        r = requests.post(self.url + '/authenticate', json={
            'email': username,
            'password': password
        })

        j = r.json()

        if j['success'] != True:
            raise Exception('Authentication failed: ' + j['message'])

        self.auth = j

        return j

    def register_cab(self, name):
        if not self.auth:
            raise Exception('You need to authenticate first')

        r = requests.post(self.url + '/api/arcade-cabs/create', json={
            'token': self.auth['token'],
            'name': name
        })

        j = r.json()

        if j['success'] != True:
            raise Exception('Cab creation failed: ' + j['message'])

        return j

    def check_cab_token(self):
        pass

    def broadcast(self):
        try:
            data = {
                'apiKey': self.key,
                'ip': self.config.webserver.host + ":" + str(self.config.webserver.port)
            }

            r = requests.post(self.config.padmiss_api_url + 'api/arcade-cabs/broadcast', json=data)

            j = r.json()
            if j['success'] != True:
                raise Exception('No ok status: ' + r.text)

            return True
        except Exception as e:
            log.debug('Broadcast failed: ' + str(e))
            return False

    def get_player(self, playerId=None, rfidUid=None, nickname=None):
        filter = {}
        if playerId:
            filter['_id'] = playerId
        if rfidUid:
            filter['rfidUid'] = rfidUid
        if nickname:
            filter['nickname'] = nickname

        result = self.graph.execute('''
        {
          Players (queryString: ''' + json.dumps(json.dumps(filter)) + ''') {
            docs {
              _id
              nickname
              shortNickname
              avatarIconUrl
              playerLevel
              playerExperiencePoints
              globalLadderRank
              globalLadderRating
              accuracy
              stamina
              totalSteps
              totalPlayTimeSeconds
              totalSongsPlayed
              metaData
            }
          }
        }
        ''')

        data = json.loads(result)
        if 'data' not in data:
            return None

        if not data['data']['Players'] or len(data['data']['Players']['docs']) != 1:
            return None

        return Player(**data['data']['Players']['docs'][0])

    def get_last_sore(self, playerId):
        filter = {"player": playerId}
        req = '''
        {
          Scores (sort: "-playedAt", limit: 1, queryString: ''' + json.dumps(json.dumps(filter)) + ''') {
            docs {
              scoreValue
              originalScore
              noteSkin
              playedAt
              modsTurn
              modsTransform
              modsOther {
                name
                value
              }
              speedMod {
                type
                value
              }
            }
          }
        }
        '''

        result = self.graph.execute(req)
        scores = json.loads(result)

        if 'data' not in scores or not scores['data']['Scores']['docs']:
            return None

        if len(scores['data']['Scores']['docs']) > 0:
            return scores['data']['Scores']['docs'][0]

        return None

    def get_score_history(self, playerId):
        myFilter = {"player": playerId}
        left = 0
        offset = 0
        scores = []

        while True:
            print(left, offset)

            req = '''
            {
               Scores (limit: 10, sort: "-playedAt", offset: ''' + str(offset) + ''', queryString: ''' + json.dumps(json.dumps(myFilter)) + ''')
               {
                  totalDocs
                  docs {
                     _id
                     playedAt
                     scoreValue
                     stepChart {
                        _id
                     }
                  }
               }
            }
            '''

            result = self.graph.execute(req)
            scoreResult = json.loads(result)

            if 'data' not in scoreResult or not scoreResult['data']['Scores']['docs']:
                left = 0
            else:
                left = len(scoreResult['data']['Scores']['docs'])
                scores += scoreResult['data']['Scores']['docs']
                offset += 10
                print("Loading score history: " + str(offset) + " / " + str(scoreResult['data']['Scores']['totalDocs']))

            if left == 0 or offset > 100:
                break

    #     populate songs
        songs = {}
        for score in scores:
            songs[score['stepChart']['_id']] = None

        i = 0
        num = len(songs.keys())
        for id in songs.keys():
            print('Populating stepchart data: ' + str(i) + ' / ' + str(num))
            i += 1

            req = '''{
                Stepchart (id: "''' + id + '''")
                {
                    song {
                        title
                        artist
                    }
                    groups
                    difficultyLevel
                    stepData
                }
            }'''
            result = self.graph.execute(req)
            songs[id] = json.loads(result)['data']['Stepchart']
            songs[id]['scores'] = list(filter(lambda s: s['stepChart']['_id'] == id, scores))

        return songs

    def post_score(self, player, upload):
        data = {
            'apiKey': self.key,
            'playerId': player._id,
            'scoreValue': upload.score.scoreValue,
            'passed': upload.score.passed,
            'secondsSurvived': upload.score.secondsSurvived,
            'group': upload.group
        }
        data.update(upload.score.scoreBreakdown.__dict__)
        data.update(upload.song.__dict__)
        data.update({k: v for k, v in upload.__dict__.items() if not isinstance(v, FlattenedBase)})

        data['inputEvents'] = list(map(lambda e: e.__dict__, upload.inputEvents))
        data['noteScoresWithBeats'] = list(map(lambda e: e.__dict__, upload.noteScoresWithBeats))


        dumpable = lambda v: v.__dict__ if isinstance(v, Base) else v
        r = requests.post(self.url + '/post-score', json={k: dumpable(v) for k, v in data.items() if v is not None})
        j = r.json()
        if j['success'] != True:
            raise TournamentApiError(j['message'])