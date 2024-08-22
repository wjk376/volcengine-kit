# volcengine-kit

## 使用说明
### 创建客户端
```python
from volcengine_kit import VolcMLPlatformClient

client = VolcMLPlatformClient(
    access_key_id='your AK',
    secret_access_key='your SK',
    iam_user_id='your IAM user ID',
    bot_app_id='your bot App ID',
    bot_app_secret='your bot App secret',
)
```

### 提交机器学习平台自定义任务
```python
task = client.submit_task(
    name='your_task_name',
    enable_range_type='Public',
    image_repo='vemlp-cn-beijing.cr.volces.com/preset-images/python',
    image_tag='3.10',
    commands=[
        'sleep 30',
        'echo hello world',
    ],
    default_qid='your default resource queue ID',
    backup_qids=[
        'backup resource queue ID 0',
        'backup resource queue ID 1',
    ],
    priority=4,
    flavor_id='your_flavor_id',
    vepfs_sub_paths=[
        '/fs_users',
        '/fs_projects',
    ],
    envs=[
        {'name': 'ENV0', 'value': 'test', 'is_private': True},
        {'name': 'ENV1', 'value': 'test', 'is_private': False},
    ],
    notify_upon_creation=True,
    notify_upon_termination=True,
    group_chat_ids=[
        'your group chat ID 0',
        'your group chat ID 1',
    ],
)
```

### 等待任务运行结束
```python
async def execute_task(...):
    # 前置业务逻辑
    ...

    # 提交任务并等待
    task = client.submit_task(...)
    await task.finished()

    # 后置业务逻辑
    ...
```