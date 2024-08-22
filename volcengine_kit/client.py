import json
from functools import wraps
from typing import Dict, Optional, List, Literal, Union

from loguru import logger
from volcengine.Credentials import Credentials
import lark_oapi as lark

from ._service import (
    VolcMLPlatformService, 
    InvalidTaskIdError,
    CallVolcAPIError,
)
from .task import VolcMLPlatformTask
from .data._receive import (
    GetResourceQueueResultModel,
    FlavorsByZone,
)
from .data._send import (
    VepfsStorageModel,
    EnvModel,
    ImageSpecModel,
    TaskRoleSpecModel,
    ResourceSpecModel,
    TaskFormModel,
)


def handle_exceptions(func):
    @wraps(func)
    def wrapper(*args, **kwds):
        handle = kwds.pop('handle_exceptions', False)
        if handle:
            try:
                return func(*args, **kwds)
            except Exception as e:
                logger.exception(e)
                return
        else:  # do nothing
            return func(*args, **kwds)
    return wrapper
    
    
class VolcMLPlatformClient:
    def __init__(
        self, 
        access_key_id: str, 
        secret_access_key: str,
        iam_user_id: Union[int, str],
        connection_timeout: int = 10,
        socket_timeout: int = 10,
        bot_app_id: Optional[str] = None,
        bot_app_secret: Optional[str] = None,
    ) -> None:
        self._credentials = Credentials(
            ak=access_key_id,
            sk=secret_access_key,
            service='ml_platform',
            region='cn-beijing',
        )
        if isinstance(iam_user_id, str):
            iam_user_id = int(iam_user_id)
        self._iam_user_id = iam_user_id
        self._connection_timeout = connection_timeout
        self._socket_timeout = socket_timeout
        self._service = VolcMLPlatformService(
            credentials=self._credentials,
            connection_timeout=self._connection_timeout,
            socket_timeout=self._socket_timeout,
        )
        self._lark_client = None
        if bot_app_id is not None and bot_app_secret is not None:
            self._lark_client = lark.Client.builder() \
                .app_id(bot_app_id) \
                .app_secret(bot_app_secret) \
                .build()
    
    def _find_optimal_queue(
        self,
        default_qid: str,
        flavor_id: str,
        flavors_by_zone: FlavorsByZone,
        backup_qids: List[str] = [],
        cpu_buffer: int = 0,
        memory_buffer: int = 0,
        volume_buffer: int = 5,
    ) -> GetResourceQueueResultModel:
        """Use default queue if it meets resource requirements of the provided buffer,
        otherwise check each backup queue.
        """
        if not isinstance(flavor_id, str):
            raise TypeError(
                f'Expected string type flavor ID but got {flavor_id.__class__.__qualname__}'
            )
        if any(
            (not isinstance(x, (int, float))) or (x < 0) 
            for x in [cpu_buffer, memory_buffer, volume_buffer]
        ):
            raise TypeError('Resource buffers must be non-negative numbers')
        
        def is_queue_vacant(q: GetResourceQueueResultModel) -> bool:
            zone_flavors = flavors_by_zone[q.ZoneId]
            if flavor_id not in zone_flavors:
                raise ValueError(
                    f'Flavor {flavor_id} not in zone `{q.ZoneId}` of queue {q}'
                )
            flavor = zone_flavors[flavor_id]
            if flavor.Deprecated:
                raise ValueError(f'{flavor} is deprecated')
            if not q.fit_flavor(flavor):
                raise ValueError(f'{q} does not fit {flavor}')
            return q.is_vacant_for(flavor, cpu_buffer, memory_buffer, volume_buffer)
                        
        default_q = self._service.get_resource_queue(default_qid)
        if is_queue_vacant(default_q):
            return default_q
                            
        # Loop through backup queues and find if any is available.
        for backup_qid in backup_qids:
            try:
                backup_q = self._service.get_resource_queue(backup_qid)
                backup_q_vacant = is_queue_vacant(backup_q)
            except Exception as e:
                # Omit errors in backup queues.
                logger.warning(e)
                continue
            else:
                if backup_q_vacant:
                    logger.info(f'Using backup {backup_q}')
                    return backup_q
        # Default plan is to use default queue even if it is not vacant for now.
        return default_q
    
    def _validate_image(self, repo: str, tag: str) -> str:
        if any(not isinstance(x, str) for x in (repo, tag)):
            raise TypeError('Image repo and tag must be string type')
        model = self._service.get_image_repo(repo)
        url = f'{repo}:{tag}'
        if url not in model.Tags:
            raise ValueError(f'`{tag}` does not exist in image repo [{repo}]')
        return url
    
    def _build_vepfs_storages(
        self, 
        sub_paths: List[str], 
        qid: str,
    ) -> List[VepfsStorageModel]:
        if (
            not isinstance(sub_paths, list)
            or
            any(not isinstance(x, str) for x in sub_paths)
        ):
            raise TypeError('vePFS sub paths must be list of strings')
        
        if len(sub_paths) == 0:
            return []
        
        mount = self._service.get_vepfs_mount(qid)
        storages = []
        
        for path in sub_paths:  # eg. `/fs_users`
            if path in mount.ReadWriteDirectories:
                read_only = False
            elif path in mount.ReadOnlyDirectories:
                read_only = True
            else:
                dirs = mount.ReadWriteDirectories + mount.ReadOnlyDirectories
                raise ValueError(f'`{path}` not in vePFS directories {dirs}')
            model = VepfsStorageModel(
                type=mount.StorageType,
                mount_path=f'/{mount.VepfsName}{path}',
                vepfs_name=mount.VepfsName,
                read_only=read_only,
                sub_path=path[1:],
                vepfs_id=mount.VepfsId,
                vepfs_host_path=f'/mnt/{mount.VepfsName}',
            )
            storages.append(model)

        return storages
    
    @handle_exceptions   
    def submit_task(
        self, 
        *,
        name: str,
        description: str = '',
        tags: List[str] = [],
        enable_range_type: Literal['Public', 'Private'] = 'Public',
        image_repo: str,
        image_tag: str,
        commands: List[str] = [],
        default_qid: str,
        backup_qids: List[str] = [],
        priority: int = 6,
        preemptible: bool = False,
        role_name: str = 'worker',
        flavor_id: str,
        cpu_buffer: int = 0,
        memory_buffer: int = 0,
        volume_buffer: int = 5,
        vepfs_sub_paths: List[str] = [],
        envs: List[Dict[str, Union[str, bool]]] = [],
        active_deadline_hours: int = 240,
        delay_exit_time_minutes: int = 0,
        tracking_interval: Union[int, float] = 10,
        print_progress: bool = False,
        print_task_params: bool = False,
        notify_upon_creation: bool = True,
        notify_upon_termination: bool = True,
        group_chat_ids: List[str] = [],
        handle_exceptions: bool = False,
        **kwds,
    ) -> VolcMLPlatformTask:
        """Create task in optimal queue on volc ML platform."""
        # Build task parameters.
        image_url = self._validate_image(image_repo, image_tag)
        flavors_by_zone = self._service.list_flavors()
        q = self._find_optimal_queue(
            default_qid=default_qid,
            flavor_id=flavor_id,
            flavors_by_zone=flavors_by_zone,
            backup_qids=backup_qids,
            cpu_buffer=cpu_buffer,
            memory_buffer=memory_buffer,
            volume_buffer=volume_buffer,
        )        
        vepfs_storages = self._build_vepfs_storages(vepfs_sub_paths, q.Id)
        
        # Submit task form.
        form_model = TaskFormModel(
            name=name,
            description=description,
            tags=tags,
            enable_range_type=enable_range_type,
            image_spec=ImageSpecModel(url=image_url),
            entrypoint_path=('\n'.join(commands)),
            resource_queue_id=q.Id,
            priority=priority,
            preemptible=preemptible,
            task_role_specs=[
                TaskRoleSpecModel(
                    role_name=role_name,
                    resource_spec=ResourceSpecModel(
                        flavor_id=flavor_id,
                        zone_id=q.ZoneId,
                        gpu_type=flavors_by_zone[q.ZoneId][flavor_id].GPUType,
                    ),
                )
            ],
            storages=vepfs_storages,
            envs=[EnvModel(**v) for v in envs],
            active_deadline_seconds=(active_deadline_hours * 60 * 60),
            delay_exit_time_seconds=(delay_exit_time_minutes * 60),
        )
        form = form_model.model_dump(
            mode='json', by_alias=True, exclude_none=True,
        )
        if print_task_params:
            logger.info(f'Task parameters:\n{json.dumps(form, indent=4)}')
        
        return VolcMLPlatformTask(
            form=form,
            queue=q,
            credentials=self._credentials,
            tracking_interval=tracking_interval,
            print_progress=print_progress,
            connection_timeout=self._connection_timeout,
            socket_timeout=self._socket_timeout,
            lark_client=self._lark_client,
            notify_upon_creation=notify_upon_creation,
            notify_upon_termination=notify_upon_termination,
            group_chat_ids=group_chat_ids,
        )
        
    def stop_task(self, task_id: str) -> bool:
        """Send stop task signal to platform."""  
        # Inspect the task before sending signal.    
        try:
            status = self._service.query_task(task_id)
        except InvalidTaskIdError as e:
            logger.error(e)
            return False
        
        if status.CreatorUserId != self._iam_user_id:
            logger.warning(f'Attempting to stop task {task_id} created by other user')
        if status.State in [
            'Success', 'Failed', 'Cancelled', 'Killed', 'Exception', 
        ]:
            logger.warning(f'Attempting to stop task {task_id} in `{status.State}` state')
        
        # Send stop signal.
        try:
            self._service.call_api(
                api='StopCustomTask', 
                form={'Id': task_id, 'EnableDiagnosis': False},
            )
        except CallVolcAPIError as e:
            if e.code == 'UnauthorizedOperation':
                logger.error(e)
                return False
            else:
                raise
        else:
            logger.success(f'Requested to stop task {task_id}')
            return True
        
    def delete_task(self, task_id: str) -> bool:
        # Inspect the task before sending signal.    
        try:
            status = self._service.query_task(task_id)
        except InvalidTaskIdError as e:
            logger.error(e)
            return False
        
        if status.CreatorUserId != self._iam_user_id:
            logger.warning(f'Attempting to delete task {task_id} created by other user')

        # Send delete signal.
        try:
            self._service.call_api(
                api='DeleteCustomTask', 
                form={'Id': task_id, 'EnableDiagnosis': False},
            )
        except CallVolcAPIError as e:
            if e.code in ['UnauthorizedOperation', 'CustomTaskNotInTerminalState']:
                logger.error(e)
                return False
            else:
                raise
        else:
            logger.success(f'Requested to delete task {task_id}')
            return True
    
    