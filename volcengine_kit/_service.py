import json
from typing import Dict, Any, List, Optional

from loguru import logger
from volcengine.base.Service import Service
from volcengine.auth.SignerV4 import SignerV4
from volcengine.ApiInfo import ApiInfo
from volcengine.ServiceInfo import ServiceInfo
from volcengine.Credentials import Credentials

from .data._receive import (
    GetResourceQueueResultModel,
    GetCustomTaskResultModel,
    FlavorModel,
    FlavorsByZone,
    VepfsMountModel,
    GetImageRepoResultModel,
)


ACTIONS = (
    'CreateCustomTask', 
    'GetCustomTask', 
    'ListCustomTasks', 
    'StopCustomTask',
    'GetContainerLogs', 
    'DeleteCustomTask', 
    'GetCustomTaskInstances',
    'GetResourceQueue', 
    'ListResourceQueues', 
    'GetMetrics', 
    'ListImageRepos',
    'GetImageRepo', 
    'ListMountPoints',
    'ListFlavorsV2',
    'GetUserVepfsFilesetPermission',
)

def _build_api_info(action: str) -> ApiInfo:
    return ApiInfo(
        method='POST', path='/', query={'Action': action, 'Version': '2021-10-01'},
        form={}, header={},
    )


class CallVolcAPIError(Exception):
    def __init__(self, api: str, error: Dict[str, Any]) -> None:
        self.api = api
        self.code = error.get('Code', '')
        self.codeN = error.get('CodeN')
        self.message = error.get('Message', '')
        
    def __str__(self) -> str:
        return f'Calling `{self.api}` failed: [{self.code}] {self.message}'
    
    
class InvalidTaskIdError(Exception):
    pass
    

class VolcMLPlatformService(Service):
    """A class that wraps common functionalities of platform."""
    def __init__(
        self, 
        credentials: Credentials,
        connection_timeout: int = 10,
        socket_timeout: int = 10,
    ) -> None:
        service_info = ServiceInfo(
            host='open.volcengineapi.com',
            header={'Accept': 'application/json'},
            credentials=credentials,
            connection_timeout=connection_timeout,
            socket_timeout=socket_timeout,
            scheme='http',
        )
        api_info = {action: _build_api_info(action) for action in ACTIONS}
        super().__init__(service_info, api_info)
    
    def call_api(
        self, 
        api: str, 
        form: Dict[str, Any],
        **kwds,
    ) -> Dict[str, Any]:
        """Overload original `json` method."""
        try:
            if api not in self.api_info:
                raise ValueError(f'Unregistered API `{api}`')
            api_info = self.api_info[api]
            body = json.dumps(form)
            r = self.prepare_request(api_info, params={})
            r.headers['Content-Type'] = 'application/json'
            r.body = body

            SignerV4.sign(r, self.service_info.credentials)

            url = r.build()
            resp = self.session.post(
                url, 
                headers=r.headers, 
                data=r.body,
                timeout=(
                    self.service_info.connection_timeout, 
                    self.service_info.socket_timeout,
                ),
            )
            resp_data = resp.json()
            if resp.status_code != 200:
                resp_meta = resp_data.get('ResponseMetadata', {})
                raise CallVolcAPIError(
                    api=api, error=resp_meta.get('Error', {})
                )
            elif 'Result' not in resp_data:
                raise CallVolcAPIError(
                    api=api, 
                    error={
                        'Code': 'MissingResult',
                        'Message': 'Successful response but missing key: `Result`',
                    },
                )
        except CallVolcAPIError as e:
            raise
        except Exception as e:
            raise CallVolcAPIError(
                api=api, error={'Code': 'Other', 'Message': str(e)},
            ) from e
        else:
            return resp_data['Result']
        
    def get_vepfs_mount(self, qid: str) -> VepfsMountModel:
        resp = self.call_api(
            api='ListMountPoints', 
            form={'StorageType': 'Vepfs', 'ResourceQueueId': qid},
        )
        vepfs_mount = None
        for mount in resp.get('List', []):
            if 'VepfsId' in mount and mount.get('Status') == 'Running':
                # XXX Only care about the first valid one.
                fs = self._get_vepfs_fileset(vepfs_id=mount['VepfsId'])
                vepfs_mount = VepfsMountModel(
                    ReadWriteDirectories=fs['ReadWriteDirectories'],
                    ReadOnlyDirectories=fs['ReadOnlyDirectories'],
                    **mount,
                )
                break
            
        if vepfs_mount is None:
            logger.error(f'Failed to get vePFS mount from:\n{resp}')
            raise ValueError(f'Failed to get vePFS mount for queue {qid}')
        return vepfs_mount
    
    def _get_vepfs_fileset(self, vepfs_id: str) -> Dict[str, List[str]]:
        resp = self.call_api(
            api='GetUserVepfsFilesetPermission', form={'VepfsIds': [vepfs_id]},
        )
        return resp['VepfsIdToDirectories'][vepfs_id]
    
    def get_resource_queue(self, qid: str) -> GetResourceQueueResultModel:
        if not isinstance(qid, str):
            raise TypeError(
                f'Expected string type queue ID but got {qid.__class__.__qualname__}'
            )
            
        try:
            resp = self.call_api(api='GetResourceQueue', form={'Id': qid})
        except CallVolcAPIError as e:
            if e.code in ('InvalidParameter', 'ResourceNotFound'):
                raise ValueError(f'Resource queue [{qid}] does not exist') from None
            else:
                raise
            
        if resp.get('Role', '') == '':
            raise ValueError(f'Invalid role for queue {qid}')
        if resp.get('State') != 'Running':
            raise ValueError(f'Invalid state `{resp.get("State")}` for queue {qid}')
        return GetResourceQueueResultModel(**resp)
            
    def list_flavors(self) -> FlavorsByZone:
        resp = self.call_api(api='ListFlavorsV2', form={'DisplayType': 'Scheduling'})        
        flavors_by_zone = {}
        for zone_id, raw_zone_flavors in resp.get('List', {}).items():
            zone_flavors = {}
            for raw_type_flavors in raw_zone_flavors.values():
                for raw_flavor in raw_type_flavors:
                    flavor = FlavorModel(**raw_flavor)
                    zone_flavors[flavor.Id] = flavor
            flavors_by_zone[zone_id] = zone_flavors
        
        return flavors_by_zone

    def query_task(self, task_id: str) -> GetCustomTaskResultModel:
        if not isinstance(task_id, str):
            raise TypeError(
                f'Expected string type task ID but got {task_id.__class__.__qualname__}'
            )
            
        try:
            resp = self.call_api('GetCustomTask', form={'Id': task_id})
            return GetCustomTaskResultModel(**resp)
        except CallVolcAPIError as e:
            if e.code in ('InvalidParameter', 'ResourceNotFound'):
                raise InvalidTaskIdError(f'Custom task [{task_id}] does not exist') from None
            else:
                raise
        
    def get_image_repo(self, repo: str) -> GetImageRepoResultModel:
        try:
            resp = self.call_api(api='GetImageRepo', form={'Id': repo})
            return GetImageRepoResultModel(**resp)
        except CallVolcAPIError as e:
            if e.code in ('InvalidParameter', 'ResourceNotFound'):
                raise ValueError(f'Image repo [{repo}] does not exist') from None
            else:
                raise