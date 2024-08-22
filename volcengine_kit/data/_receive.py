from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, model_validator, Field


class QuotaItemModel(BaseModel):
    VCPU: int
    Memory: int
    GPUResources: Dict[str, int]
    RdmaEniCount: int
    
    
class VolumeItemModel(BaseModel):
    Id: str
    Num: int
    ZoneId: str
    Name: str
    
    
class VepfsMountModel(BaseModel):
    StorageType: Literal['Vepfs']
    VepfsName: str
    VepfsId: str
    Status: str
    ReadWriteDirectories: List[str]
    ReadOnlyDirectories: List[str]
    
    
class FlavorModel(BaseModel):
    Name: str
    Id: str
    Type: Literal['通用型', '计算型', '内存型', 'GPU型', '高性能计算GPU型']
    Deprecated: bool
    SupportVolumeTypeId: str
    vCPU: int
    Memory: int
    GPUType: str
    GPUMemory: int
    GPUNum: int
    MaxSlicesPerGPU: int
    EniCount: int
    NetQuota: str
    
    @model_validator(mode='before')
    @classmethod
    def fields_check(cls, data):
        id_ = data.get('Id', '')
        if id_.startswith('ml.xni'):
            data['GPUType'] = 'X3C'
        return data
    
    def __str__(self) -> str:
        return f'[flavor ID={self.Id} type={self.Type}]'
    

FlavorsByZone = Dict[str, Dict[str, FlavorModel]]


class GetResourceQueueResultModel(BaseModel):
    Id: str
    Name: str
    Description: str
    ClusterId: str
    ZoneId: str
    DevZoneId: str
    State: str
    Role: str
    ResourceGroupId: str
    CapableFlavorTypes: str
    Shareable: bool
    SupportMGPU: bool
    QuotaCapability: QuotaItemModel
    QuotaAllocated: QuotaItemModel
    VolumeCapability: List[VolumeItemModel]
    VolumeAllocated: List[VolumeItemModel]
    
    def __str__(self) -> str:
        return f'[resource queue ID={self.Id} name={self.Name}]'
    
    @property
    def total_cpu(self) -> int:
        return self.QuotaCapability.VCPU
    
    @property
    def allocated_cpu(self) -> int:
        return self.QuotaAllocated.VCPU
    
    @property
    def vacant_cpu(self) -> int:
        return self.total_cpu - self.allocated_cpu
    
    @property
    def total_memory(self) -> int:
        return self.QuotaCapability.Memory
    
    @property
    def allocated_memory(self) -> int:
        return self.QuotaAllocated.Memory
    
    @property
    def vacant_memory(self) -> int:
        return self.total_memory - self.allocated_memory
    
    def total_gpu(self, type: str) -> int:
        return self.QuotaCapability.GPUResources.get(type, 0)
    
    def allocated_gpu(self, type: str) -> int:
        return self.QuotaAllocated.GPUResources.get(type, 0)
    
    def vacant_gpu(self, type: str) -> int:
        return self.total_gpu(type) - self.allocated_gpu(type)
    
    @property
    def vacant_volume(self) -> int:
        total = sum(x.Num for x in self.VolumeCapability)
        allocated = sum(x.Num for x in self.VolumeAllocated)
        return total - allocated
    
    def fit_flavor(self, flavor: FlavorModel) -> bool:
        """Check if the capacity of queue can hold provided flavor."""
        if flavor.Type == '高性能计算GPU型':
            return False
        cpu_ok = (self.total_cpu >= flavor.vCPU)
        memory_ok = (self.total_memory >= flavor.Memory)
        if flavor.Type == 'GPU型':
            gpu_ok = (self.total_gpu(type=flavor.GPUType) >= flavor.GPUNum)
        else:
            gpu_ok = True
        return cpu_ok and memory_ok and gpu_ok
    
    def is_vacant_for(
        self, 
        flavor: FlavorModel,
        cpu_buffer: int = 0,
        memory_buffer: int = 0,
        volume_buffer: int = 5,
    ) -> bool:
        """Check if vacant resources in queue allow provided flavor."""
        if flavor.Type == '高性能计算GPU型':
            return False
        if flavor.Type == 'GPU型':
            gpu_ok = (self.vacant_gpu(flavor.GPUType) >= flavor.GPUNum)
        else:
            gpu_ok = True
        cpu_ok = (self.vacant_cpu >= flavor.vCPU + cpu_buffer)
        memory_ok = (self.vacant_memory >= flavor.Memory + memory_buffer)
        volume_ok = (self.vacant_volume >= volume_buffer)
        return gpu_ok and cpu_ok and memory_ok and volume_ok
    
    
class GetImageRepoResultModel(BaseModel):
    Id: str
    Namespace: str
    Name: str
    Preset: bool
    CreateTime: str
    UpdateTime: str
    Purposes: List[str]
    Tags: List[str]
    Domain: str
    Labels: List[str]
    Registry: str
    
    
class GetCustomTaskResultModel(BaseModel):
    Id: str
    Name: str
    Description: str
    Tags: List[str] = Field(default_factory=list)
    State: str
    CacheType: str
    ClusterId: str
    CreatorUserId: int
    ResourceGroupId: str
    ResourceQueueId: str
    DiagInfo: str
    ExitCode: int
    HasPermission: bool
    CreateTime: Optional[datetime]
    LaunchTime: Optional[datetime]
    FinishTime: Optional[datetime]
    UpdateTime: Optional[datetime]

    @model_validator(mode='before')
    @classmethod
    def fields_check(cls, data):
        get_datetime = (
            lambda x: None if x == '' else datetime.strptime(x, '%Y-%m-%dT%H:%M:%SZ')
        )
        data['CreateTime'] = get_datetime(data.get('CreateTime', ''))
        data['LaunchTime'] = get_datetime(data.get('LaunchTime', ''))
        data['FinishTime'] = get_datetime(data.get('FinishTime', ''))
        data['UpdateTime'] = get_datetime(data.get('UpdateTime', ''))
        return data