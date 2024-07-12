import os
from typing import List
import logging
import requests

from notifications.common import NotificationClient, Resource
from notifications.fields.blocks import BaseBlock
from notifications.fields.attachments import Attachment
from notifications.mattermost.converter import MattermostConverter

ACCESS_TOKEN = None
ACCESS_TOKEN_ENV_NAME = 'SLACK_ACCESS_TOKEN'
BASE_URL = None
BASE_URL_ENV_NAME = 'MATTERMOST_URL'
TEAM_ID = None
TEAM_ID_ENV_NAME = 'SLACK_ACCESS_TOKEN'

logger = logging.getLogger(__name__)


class MattermostError(requests.exceptions.RequestException):
    pass


class MattermostMessage:
    def __init__(self, client, response,
                 text: str = None,
                 raise_exc=False,
                 attachments: List = None,
                 blocks: List = None):
        self._client = client
        self._response = response
        self._raise_exc = raise_exc

        self.text = text
        self.attachments = attachments or []
        self.blocks = blocks or []

    @property
    def response(self):
        return self._response

    def send_to_thread(self, **kwargs):
        json = self._response.json()
        message_id = json['id']
        kwargs.update(thread_ts=message_id)

        message = self._client.send_notify(json['channel_id'], **kwargs)

        return message

    def update(self):
        json = self._response.json()
        data = {
            'id': json['id'],
            'message': self.text or '',
            'props': {},
            'metadata': {}
        }
        if self.blocks:
            data['message'] += ''.join(map(str, self.blocks))

        if self.attachments:
            data['props']['attachments'] = [a.convert() for a in self.attachments]

        return self._client.call_resource(
            Resource('posts/{post_id}', 'PUT'),
            json=data, raise_exc=self._raise_exc,
        )

    def delete(self):
        message_id = self._response.json()['id']
        response = self._client.call_resource(
            Resource(f'posts/{message_id}', 'DELETE'),
            raise_exc=self._raise_exc
        )
        return response

    def upload_file(self, file, **kwargs):
        pass

    def add_reaction(self, name, raise_exc=False):
        json = self._response.json()
        data = {
            'emoji_name': name,
            'post_id': json['id'],
            'user_id': json['user_id'],
            'create_at': json['create_at']
        }
        return self._client.call_resource(
            Resource('reactions', 'POST'),
            json=data, raise_exc=raise_exc,
        )

    def remove_reaction(self, name, raise_exc=False):
        json = self._response.json()
        user_id = json['user_id']
        post_id = json['post_id']

        return self._client.call_resource(
            Resource(f'users/{user_id}/posts/{post_id}/reactions/{name}', 'DELETE'),
            raise_exc=raise_exc,
        )


class Mattermost(NotificationClient):

    def __init__(self, base_url, *, token, team_id=None):
        super(Mattermost, self).__init__(base_url, token=token)
        self._team_id = team_id

    def channel_id_by_name(self, channel_name):
        response = self.call_resource(Resource(f'teams/{self._team_id}/channels/name/{channel_name}', 'GET'))

        if response.status_code != 200:
            raise ValueError('Channel not found')

        return response.json()['id']

    def set_team_id_by_name(self, team_name):
        response = self.call_resource(Resource('teams', 'GET'))
        json = response.json()
        for item in json:
            if item['name'] == team_name:
                self._team_id = item['id']
                break

    @classmethod
    def from_env(cls):
        token = ACCESS_TOKEN or os.getenv(ACCESS_TOKEN_ENV_NAME)
        base_url = BASE_URL or os.getenv(BASE_URL_ENV_NAME)
        team_id = TEAM_ID or os.getenv(TEAM_ID_ENV_NAME)

        return cls(base_url, token=token, team_id=team_id)

    def send_notify(self,
                    channel, *,
                    text: str = None,
                    username: str = None,
                    icon_url: str = None,
                    icon_emoji: str = None,
                    link_names: bool = True,
                    raise_exc: bool = False,
                    attachments: List[Attachment] = None,
                    blocks: List[BaseBlock] = None,
                    thread_ts: str = None):
        if not thread_ts:
            channel = self.channel_id_by_name(channel)

        data = {
            'channel_id': channel,
            'message': text or '',
            'props': {},
            'metadata': {}
        }
        converter = MattermostConverter()
        converter.convert(blocks=blocks)

        if blocks:
            data['message'] += converter.message

        if thread_ts:
            data['root_id'] = thread_ts

        data['props']['attachments'] = []
        if converter.attachments_result:
            data['props']['attachments'].extend(converter.attachments_result)
        if attachments:
            data['props']['attachments'].extend([a.to_dict() for a in attachments])

        response = self.call_resource(
            Resource('posts', 'POST'), json=data,
        )
        return MattermostMessage(
            self, response, text=text, raise_exc=raise_exc,  blocks=blocks, attachments=attachments
        )

    def upload_file(self,
                    channel, file, *,
                    title: str = None,
                    content: str = None,
                    filename: str = None,
                    thread_ts: str = None,
                    filetype: str = 'text',
                    raise_exc: bool = False):
        pass