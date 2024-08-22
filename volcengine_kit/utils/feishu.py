import json
from typing import List, Literal

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest, 
    CreateMessageRequestBody,
    CreateMessageResponse,
    ListChatRequest,
    ListChatResponse,
)


def _lark_log_error(func: str, response):
    log_id = response.get_log_id()
    lark.logger.error(
        f'{func} failed, code: {response.code}, msg: {response.msg}, log_id: {log_id}'
    )
    
    
def create_message(
    client: lark.Client, 
    receive_id_type: Literal['open_id', 'union_id', 'user_id', 'email', 'chat_id'],
    receive_id: str, 
    msg_type: str,
    content: str,
) -> CreateMessageResponse:
    request = CreateMessageRequest.builder() \
        .receive_id_type(receive_id_type) \
        .request_body(
            CreateMessageRequestBody.builder() \
                .receive_id(receive_id) \
                .msg_type(msg_type) \
                .content(content) \
                .build() \
        ).build()
    response = client.im.v1.message.create(request)
    if not response.success():
        _lark_log_error(func='client.im.v1.message.create', response=response)
    return response
        
        
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