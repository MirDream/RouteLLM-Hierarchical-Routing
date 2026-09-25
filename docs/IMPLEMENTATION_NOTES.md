# 分层资源感知 RouteLLM 实验实现说明

## 实现结论

本实现以 RouteLLM 0.2.0 baseline 为基础，保留原有 two-model Router、Controller 和示例，不删除也不改写其核心逻辑。在旁路新增一个实验性的 Hierarchical Resource-Aware LLM Router，将决策拆成能力路由和资源调度两层。

第一层对多个模型计算 capability score 并返回 Top-K。第二层获取模拟资源状态，对每个可行的 Model×Node 组合计算综合 utility，最终选择效用最高的模型与执行节点。推理边界采用可注入 `inference_client`，因此当前 demo 可以离线运行，之后也能接入 LiteLLM 或真实推理服务。

## 总体流程

```text
Query
  -> QueryEncoder
  -> MultiModelRouter
  -> Top-K candidate models
  -> SimulatedResourceMonitor snapshot
  -> ResourceAwareScheduler
  -> best Model x Node pair
  -> inference_client
  -> Response
```

## 第一层能力路由

`QueryEncoder` 提取 token 数量估计、复杂度、代码信号、数学信号和非 ASCII 字符比例。`MultiModelRouter` 结合模型能力先验、模型能力层级与 Query 复杂度的匹配程度，以及可选的专业领域关键词，生成 `[0, 1]` 范围的 capability score。

所有模型按 capability score 降序排序，返回 Top-K，而不是原 RouteLLM 的 strong/weak 二选一。原 `routellm/routers/routers.py` 保持不变，旧 baseline 仍可独立运行。

## 第二层资源调度

`SimulatedResourceMonitor` 返回每个节点的：GPU 利用率、总显存、空闲显存、队列长度、网络延迟、吞吐量和可部署模型。

调度器先过滤不可行组合：节点必须部署该模型，并且空闲显存必须满足模型最低要求。对其余组合预测延迟、归一化成本并计算资源负载，然后使用：

`U = alpha × quality - beta × latency - gamma × cost - delta × resource_load`

默认权重为 `0.60 / 0.20 / 0.10 / 0.10`，四项之和强制等于 1。权重和资源状态均通过清晰接口注入，便于后续实验。

## 模块说明

| 模块 | 作用 |
|---|---|
| `routers/multimodel_router.py` | Query 特征编码、多模型能力评分、Top-K 排名 |
| `monitor/resource_monitor.py` | 资源状态接口、模拟节点状态、状态更新 |
| `scheduler/latency_predictor.py` | 根据模型基准延迟、GPU、队列、网络和吞吐预测延迟 |
| `scheduler/scoring.py` | 资源负载与 utility 公式 |
| `scheduler/resource_scheduler.py` | 可行性过滤、Model×Node 评分与最终选择 |
| `hierarchical_controller.py` | 编排两层路由、记录决策、调用推理边界 |
| `examples/hierarchical_demo.py` | 3 模型、2 节点演示 |
| `tests/test_hierarchical_router.py` | Top-K、资源反转、显存过滤和日志测试 |

## Demo 场景和结果

能力层返回 `model-a` 和 `model-b`。`model-a` 能力最高，但只能在高负载 cloud 上执行；`model-b` 能力第二，同时可以在低负载 edge-1 上执行。资源层结果如下：

| Model×Node | capability | latency ms | resource load | utility |
|---|---:|---:|---:|---:|
| `model-b@edge-1` | 0.751 | 378.214 | 0.205 | 0.321124 |
| `model-b@cloud` | 0.751 | 1104.929 | 0.855 | 0.131767 |
| `model-a@cloud` | 0.791 | 1541.429 | 0.855 | 0.089100 |

最终选择为 `model-b@edge-1`。这验证了目标情况：能力第一的模型因为资源繁忙，被能力第二但资源条件更好的模型替代。

## 决策日志

每次请求都会写入 JSONL，包含：

- query 与 query features
- capability scores 与 Top-K 排名
- 全部 resource states
- 每个可行组合的 final utility scores
- selected model
- selected node

默认 demo 日志为 `demo_output/decisions.jsonl`。

## 验证结果

共 4 个单元测试并全部通过：

1. Top-K 按能力分数正确排序。
2. 第一候选节点繁忙时，第二候选可以因更高 utility 胜出。
3. 空闲显存不足的 Model×Node 组合会被过滤。
4. Controller 日志包含要求的全部决策字段。

原 RouteLLM baseline 的离线 smoke test也再次保留，可用于回归对照。

## 运行方法

在项目根目录执行：

```powershell
.\run_demo.ps1
```

运行单元测试：

```powershell
$env:PYTHONPATH = (Get-Location).Path
& .\.venv\Scripts\python.exe -m unittest discover -s .\tests -v
```

## 当前边界和后续扩展

当前资源状态和推理响应均为模拟值，重点是验证分层接口和调度逻辑。接入真实环境时，只需实现 `ResourceMonitor.snapshot()`，并向 `HierarchicalController` 注入真实 `inference_client`。建议下一阶段加入指标归一化校准、动态权重、失败重试、节点健康检查以及基于历史数据训练的 latency predictor。
