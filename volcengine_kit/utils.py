import json
from typing import List

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest, 
    CreateMessageRequestBody,
    ListChatRequest,
    ListChatResponse,
)


def _lark_log_error(func: str, response):
    log_id = response.get_log_id()
    lark.logger.error(
        f'{func} failed, code: {response.code}, msg: {response.msg}, log_id: {log_id}'
    )
    
    
def send_group_chat_message(client: lark.Client, chat_id: str, content: str) -> None:
    request = CreateMessageRequest.builder() \
        .receive_id_type('chat_id') \
        .request_body(
            CreateMessageRequestBody.builder() \
                .receive_id(chat_id) \
                .msg_type('text') \
                .content(json.dumps({'text': content})) \
                .build() \
        ).build()
    response = client.im.v1.message.create(request)
    if not response.success():
        _lark_log_error(func='client.im.v1.message.create', response=response)


def _build_list_chat_request(page_size: int, page_token: str) -> ListChatRequest:
    return ListChatRequest.builder() \
        .page_size(page_size) \
        .page_token(page_token) \
        .build()
        

def _get_list_group_chats_response_single_page(
    client: lark.Client,
    page_size: int,
    page_token: str,
) -> ListChatResponse:
    request = _build_list_chat_request(page_size, page_token)
    response = client.im.v1.chat.list(request)
    if not response.success():
        _lark_log_error(func='client.im.v1.chat.list', response=response)
    return response   

        
def list_group_chats(client: lark.Client, page_size: int = 20) -> List[str]:
    response = _get_list_group_chats_response_single_page(
        client=client, page_size=page_size, page_token='',
    )
    if not response.success():
        return []
    chat_ids = [item.chat_id for item in response.data.items]
    page_token = response.data.page_token
    
    while page_token:
        response = _get_list_group_chats_response_single_page(
            client=client, page_size=page_size, page_token=page_token,
        )
        if not response.success():
            return chat_ids
        chat_ids.extend([item.chat_id for item in response.data.items])
        page_token = response.data.page_token
    
    return chat_ids