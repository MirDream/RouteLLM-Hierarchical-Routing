# Static Router 与 Dynamic Router 模拟实验说明

## 实验结论

在固定随机种子生成的 300 请求云边压力实验中，Static Router 将全部请求固定到 cloud，突发流量持续累积队列。Dynamic Router 在能力 Top-K 内根据实时资源状态选择 Model×Node，将 223 个请求分流到 edge-1。

在本实验参数下，Dynamic Router 相比 Static Router：

- 平均延迟降低 86.009%；
- P95 延迟降低 80.733%；
- SLA 违规率降低 73.000 个百分点；
- 总模拟推理成本降低 31.122%；
- cloud 峰值队列降低 82.071%。

这些数字用于验证调度机制，不是对真实 vLLM 吞吐或成本的预测。

## 实验设计

模拟使用固定随机种子 `20260924`，产生 300 个请求。请求分成 normal 和 burst 两类到达阶段，并混合 simple、code、reasoning、summary 四种 Query。

节点包括：

| 节点 | 模型 | 服务能力 | 特点 |
|---|---|---|---|
| cloud | model-a、model-b | 0.72 request/s | 显存大、网络延迟较高 |
| edge-1 | model-b、model-c | 1.28 request/s | 显存较小、网络延迟低 |

队列随请求到达增加，并按照节点服务率随时间衰减。GPU 利用率、空闲显存和吞吐量由当前队列派生，再送入已有的 `ResourceAwareScheduler`。

## 对比策略

Static Router 只取 capability Top-1，并使用模型的固定默认节点，不读取资源状态。本实验中所有请求最终进入 cloud。

Dynamic Router 取 capability Top-2，并对可行的 Model×Node 组合计算 utility。它可以在 cloud 空闲时使用 model-a，也能在 cloud 拥塞时选择 model-b@edge-1。

两套策略使用完全相同的请求顺序、到达间隔、输出 token 和延迟扰动，确保差异来自调度策略。

## 汇总结果

| 指标 | Static | Dynamic | 改善 |
|---|---:|---:|---:|
| Mean latency ms | 5001.464 | 699.776 | 86.009% |
| P95 latency ms | 9553.483 | 1840.650 | 80.733% |
| SLA violation rate | 87.667% | 14.667% | 73.000 pp |
| Total simulated cost | 1.079730 | 0.743700 | 31.122% |
| Peak cloud queue | 146.480 | 26.263 | 82.071% |

选择分布：

| 策略 | model-a | model-b | cloud | edge-1 |
|---|---:|---:|---:|---:|
| Static | 234 | 66 | 300 | 0 |
| Dynamic | 69 | 231 | 77 | 223 |

## 三个请求快照

| Request | Phase | Static | Static latency | Dynamic | Dynamic latency |
|---:|---|---|---:|---|---:|
| 20 | normal | model-a@cloud | 917.370 ms | model-b@edge-1 | 302.361 ms |
| 100 | burst | model-a@cloud | 3669.738 ms | model-a@cloud | 1308.971 ms |
| 230 | burst | model-a@cloud | 7485.533 ms | model-b@edge-1 | 738.935 ms |

Request 100 表明 Dynamic Router 并非永远选择 edge。在当时的能力分数和资源状态下，它仍选择 model-a@cloud，但 cloud 队列远小于 Static 系统。Request 230 则展示了突发后期的明确分流。

## 输出文件

- `simulation_output/summary.json`：实验参数、两种策略汇总和改善比例。
- `simulation_output/requests.csv`：600 条逐请求记录，每种策略各 300 条。
- `simulation/static_vs_dynamic.py`：可重复运行的模拟器。
- `tests/test_simulation.py`：比较结果与输出文件测试。

## 运行方法

```powershell
.\run_simulation.ps1
```

## 如何接入真实 vLLM

当前模拟验证的是 RouteLLM → capability router → resource scheduler → model/node 的控制链。下一阶段接入真实 vLLM 时：

1. 用 Prometheus、DCGM Exporter、NVML 或 vLLM `/metrics` 替换 `SimulatedResourceMonitor`；
2. 将节点和模型映射到两个 OpenAI-compatible vLLM endpoint；
3. 把 `inference_client` 实现为向选定 endpoint 发送 Chat Completions 请求；
4. 用真实 TTFT、TPOT、queue time、throughput 和错误率替换当前延迟估计；
5. 保留本模拟作为部署前回归测试。

不建议在第一版就直接部署两台真实机器，因为模拟已经可以验证接口、日志、分流和调度公式；真实 vLLM 应作为性能校准和系统验证阶段。
