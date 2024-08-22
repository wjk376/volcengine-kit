import asyncio
import time
import threading
from datetime import datetime
from typing import Union, Optional, List, Dict, Any

from volcengine.Credentials import Credentials
import lark_oapi as lark
from loguru import logger

from ._service import VolcMLPlatformService
from .data._receive import GetCustomTaskResultModel, GetResourceQueueResultModel
from . import utils


_terminal_task_states = [
    'Success', 
    'SuccessHolding', 
    'Failed', 
    'FailedHolding',
    'Cancelled', 
    'Killed', 
    'Exception', 
]
_DEFAULT_TRACKING_INTERVAL = 10
_MIN_TRACKING_INTERVAL = 5
_MAX_TRACKING_INTERVAL = 300


class VolcMLPlatformTask:
    """A class of tasks that have been created on platform with status tracking."""
    def __init__(
        self,
        form: Dict[str, Any],
        queue: GetResourceQueueResultModel,
        credentials: Credentials,
        tracking_interval: Union[int, float],
        print_progress: bool = False,
        connection_timeout: int = 10,
        socket_timeout: int = 10,
        lark_client: Optional[lark.Client] = None,
        notify_upon_creation: bool = True,
        notify_upon_termination: bool = True,
        group_chat_ids: List[str] = [],
        **kwds,
    ) -> None:
        self._q = queue
        self._service = VolcMLPlatformService(
            credentials=credentials,
            connection_timeout=connection_timeout,
            socket_timeout=socket_timeout,
        )
        self._lark_client = lark_client
        self._print_progress = print_progress
        
        # Inspect group chats.
        if not isinstance(group_chat_ids, list):
            logger.warning('Group chat IDs must be provided in a list')
            group_chat_ids = []

        # Create task on platform and get initial status.
        self._id = self._create_task(
            form=form,
            send_notification=notify_upon_creation,
            group_chat_ids=group_chat_ids,
        )
        self._status: GetCustomTaskResultModel = self._service.query_task(self._id)
        
        if (
            not isinstance(tracking_interval, (int, float))
            or
            not _MIN_TRACKING_INTERVAL <= tracking_interval <= _MAX_TRACKING_INTERVAL
        ):
            logger.warning(
                f'`tracking_interval` must be a number between {_MIN_TRACKING_INTERVAL} and '
                f'{_MAX_TRACKING_INTERVAL}, using default value {_DEFAULT_TRACKING_INTERVAL} '
                'instead'
            )
            tracking_interval = _DEFAULT_TRACKING_INTERVAL
        
        self._rlock = threading.RLock()
        self._track_thread = threading.Thread(
            target=self._track,
            name=f'Task {self._id} tracking',
            args=(tracking_interval, notify_upon_termination, group_chat_ids),
            daemon=True,
        )
        self._track_thread.start()
        
    def _create_task(
        self, 
        form: Dict[str, Any],
        send_notification: bool,
        group_chat_ids: List[str],
    ) -> str:
        """Submit task to ML platform and retrieve task ID."""
        resp = self._service.call_api('CreateCustomTask', form=form)
        task_id = resp.get('Id', '')
        logger.success(f'Created task {task_id} in queue {self._q.Id}')
        
        if self._lark_client is not None and send_notification:
            content = f'成功创建自定义任务[{task_id}]，所在队列[{self._q.Name}]。'
            for chat_id in group_chat_ids:
                if isinstance(chat_id, str):
                    utils.send_group_chat_message(self._lark_client, chat_id, content)
        
        return task_id
        
    @property
    def id(self) -> str:
        return self._id
    
    @property
    def name(self) -> str:
        return self._status.Name
    
    @property
    def description(self) -> str:
        return self._status.Description
    
    @property
    def tags(self) -> List[str]:
        return self._status.Tags
    
    @property
    def state(self) -> str:
        return self._status.State
    
    @property
    def queue_id(self) -> str:
        return self._status.ResourceQueueId
    
    @property
    def group_id(self) -> str:
        return self._status.ResourceGroupId
    
    @property
    def create_time(self) -> Optional[datetime]:
        return self._status.CreateTime
    
    @property
    def launch_time(self) -> Optional[datetime]:
        return self._status.LaunchTime
    
    @property
    def finish_time(self) -> Optional[datetime]:
        return self._status.FinishTime
    
    @property
    def update_time(self) -> Optional[datetime]:
        return self._status.UpdateTime
    
    def _track(
        self,
        tracking_interval: Union[int, float],
        send_notification: bool,
        group_chat_ids: List[str],
    ) -> None:
        """Intermittently query task status until it reaches a terminal state."""
        while self.state not in _terminal_task_states:
            time.sleep(tracking_interval)
            try:
                status = self._service.query_task(self._id)
                with self._rlock:
                    self._status = status
            except Exception as e:
                logger.exception(e)
            finally:
                if self._print_progress:
                    logger.info(f'Task {self.id} current state: `{self.state}`')
        
        if self._lark_client is not None and send_notification:
            content = f'自定义任务[{self.id}]运行结束，最终状态[{self.state}]。'
            for chat_id in group_chat_ids:
                if isinstance(chat_id, str):
                    utils.send_group_chat_message(self._lark_client, chat_id, content)

    async def finished(self) -> None:
        while self.state not in _terminal_task_states:
            await asyncio.sleep(1)