from typing import Optional, Literal, List, Dict, Annotated

from pydantic import BaseModel, Field, model_validator
import annotated_types


class ImageSpecModel(BaseModel):
    url: str = Field(serialization_alias='Url')
    type: Optional[Literal['Preset', 'VolcEngine', 'Custom']] = Field(
        default=None, serialization_alias='Type',
    )
    purposes: Optional[List[str]] = Field(default=None, serialization_alias='Purposes')
    mode: Optional[Literal['Init']] = Field(default=None, serialization_alias='Mode')
    
    @model_validator(mode='before')
    @classmethod
    def fields_check(cls, data):
        image_type = data.get('type')
        if image_type is not None:
            if image_type not in ('Preset', 'VolcEngine', 'Custom'):
                raise ValueError(
                    "Image type must be one of ['Preset', 'VolcEngine', 'Custom']"
                )
        
        # XXX For now we keep other fields None.
        data['purposes'] = None
        data['mode'] = None        
        return data
    
    
class ResourceSpecModel(BaseModel):
    flavor_id: str = Field(serialization_alias='FlavorID')
    zone_id: str = Field(serialization_alias='ZoneId')
    resource_slice: Optional[Dict[str, int]] = Field(
        default=None, serialization_alias='ResourceSlice',
    )
    gpu_type: str = Field(default='', serialization_alias='GPUType')
    
    
class TaskRoleSpecModel(BaseModel):
    role_name: str = Field(serialization_alias='RoleName')
    role_replicas: Literal[1] = Field(serialization_alias='RoleReplicas')
    resource_spec: ResourceSpecModel = Field(serialization_alias='ResourceSpec')
    role_min_replicas: Literal[1] = Field(serialization_alias='RoleMinReplicas')
    role_max_failed: Literal[0] = Field(serialization_alias='RoleMaxFailed')
    role_restart_policy: Literal['Never'] = Field(serialization_alias='RoleRestartPolicy')
    role_restart_max_retry_count: Literal[0] = Field(serialization_alias='RoleRestartMaxRetryCount')
    
    @model_validator(mode='before')
    @classmethod
    def fields_check(cls, data):
        data['role_replicas'] = 1
        data['role_min_replicas'] = 1
        data['role_max_failed'] = 0
        data['role_restart_policy'] = 'Never'
        data['role_restart_max_retry_count'] = 0
        return data

    
class VepfsStorageModel(BaseModel):
    type: Literal['Vepfs'] = Field(serialization_alias='Type')
    mount_path: str = Field(serialization_alias='MountPath')
    vepfs_name: str = Field(serialization_alias='VepfsName')
    read_only: bool = Field(default=False, serialization_alias='ReadOnly')
    sub_path: str = Field(serialization_alias='SubPath')
    vepfs_id: str = Field(serialization_alias='VepfsId')
    vepfs_host_path: str = Field(serialization_alias='VepfsHostPath')
    

class DiagOption(BaseModel):
    name: str = Field(serialization_alias='Name')
    enable: bool = Field(default=False, serialization_alias='Enable')
    

class EnvModel(BaseModel):
    name: str = Field(serialization_alias='Name')
    value: str = Field(serialization_alias='Value')
    is_private: bool = Field(default=False, serialization_alias='IsPrivate')
    
    
class TaskFormModel(BaseModel):
    name: str = Field(min_length=1, serialization_alias='Name')
    
    description: str = Field(default='', serialization_alias='Description')
    
    tags: List[str] = Field(default_factory=list, serialization_alias='Tags')
    
    enable_range_type: Literal['Public', 'Private'] = Field(
        default='Public', serialization_alias='EnableRangeType',
    )
    
    image_spec: ImageSpecModel = Field(serialization_alias='ImageSpec')
  
    source_code_state: Literal[-1] = Field(serialization_alias='SourceCodeState')
    
    entrypoint_path: str = Field(serialization_alias='EntrypointPath')
    
    resource_queue_id: str = Field(serialization_alias='ResourceQueueId')
    
    priority: Literal[2, 4, 6] = Field(default=6, serialization_alias='Priority')

    preemptible: bool = Field(
        default=False, 
        serialization_alias='Preemptible',
        description='Set to true might cause the task to be ceased at any time',
    )
    
    framework: Literal['Custom'] = Field(default='Custom', serialization_alias='Framework')
    
    task_role_specs: Annotated[List[TaskRoleSpecModel], annotated_types.Len(1, 1)] = Field(
        serialization_alias='TaskRoleSpecs',
    )
    
    storages: List[VepfsStorageModel] = Field(default_factory=list, serialization_alias='Storages')
    
    diag_options: Annotated[List[DiagOption], annotated_types.Len(3, 3)] = Field(
        default=[
            DiagOption(name='HostPing', enable=False),
            DiagOption(name='PythonDetection', enable=False),
            DiagOption(name='LogDetection', enable=False),
        ],
        serialization_alias='DiagOptions',
    )

    retry_options: Dict[str, bool] = Field(serialization_alias='RetryOptions')

    enable_tensorboard: bool = Field(default=False, serialization_alias='EnableTensorBoard')
    
    tensorboard_path: str = Field(default='', serialization_alias='TensorBoardPath')
    
    access_types: Annotated[List[Literal['Public', 'Private']], annotated_types.Len(1, 1)] = Field(
        serialization_alias='AccessTypes',
    )
    
    access_user_ids: Annotated[List, annotated_types.Len(0, 0)] = Field(
        serialization_alias='AccessUserIds',
    )
    
    code_source: Literal[''] = Field(serialization_alias='CodeSource')
    
    code_ori_path: Literal[''] = Field(serialization_alias='CodeOriPath')
    
    local_code_path: Literal[''] = Field(serialization_alias='LocalCodePath')
    
    tos_code_path: Literal[''] = Field(serialization_alias='TOSCodePath')
    
    envs: List[EnvModel] = Field(default_factory=list, serialization_alias='Envs')
    
    advance_args: Dict = Field(serialization_alias='AdvanceArgs')

    active_deadline_seconds: int = Field(
        default=864_000, strict=True, ge=0, lt=100_000_000, 
        serialization_alias='ActiveDeadlineSeconds',
    )
    
    delay_exit_time_seconds: int = Field(
        default=0, strict=True, ge=0, le=864_000,
        serialization_alias='DelayExitTimeSeconds',
    )
    
    @model_validator(mode='before')
    @classmethod
    def fields_check(cls, data):
        # Do some auto fills.
        data['source_code_state'] = -1
        data['retry_options'] = {'EnableRetry': False}
        data['access_types'] = [data.get('enable_range_type')]
        data['access_user_ids'] = []
        data['code_source'] = ''
        data['code_ori_path'] = ''
        data['local_code_path'] = ''
        data['tos_code_path'] = ''
        data['advance_args'] = {}
        return data