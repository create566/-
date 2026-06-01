# Redis 内存使用率过高处理方案

## 告警名称
- **告警名**: `RedisMemoryHigh`
- **告警级别**: 警告 / 严重
- **触发条件**: Redis 内存使用率超过阈值（警告≥70%，严重≥85%）

## 问题描述
当 Redis 内存使用率持续升高时，会导致：
- 写入操作失败（OOM error: "command not allowed when used memory > 'maxmemory'"）
- 键驱逐（eviction）导致缓存命中率暴跌
- 数据库查询量激增（缓存失效后的穿透效应）
- 应用响应时间显著增加
- 可能导致 Redis 进程被系统 OOM Killer 杀死

## 排查步骤

### 步骤1: 检查内存概况
```bash
redis-cli INFO memory
# 关注: used_memory_rss, maxmemory, mem_fragmentation_ratio
```

### 步骤2: 找出大 Key
```bash
redis-cli --bigkeys                    # 扫描所有大key
redis-cli MEMORY DOCTOR               # 内存诊断报告
redis-cli MEMORY USAGE <key>          # 单个key内存占用
```

### 步骤3: 分析 Key 分布
```bash
redis-cli INFO keyspace               # 各DB的key数量
redis-cli DBSIZE                      # 当前DB的key总数
```

### 步骤4: 检查过期策略
```bash
redis-cli INFO stats
# 关注: expired_keys, evicted_keys
```

### 步骤5: 检查客户端连接
```bash
redis-cli CLIENT LIST                 # 所有客户端连接
redis-cli INFO clients                # 连接数统计
```

## 常见原因分析

### 原因1: 大 Key 占用过多内存
**特征**:
- --bigkeys 扫描发现 hash/list/set 元素过多
- 单个 key 占用数十MB甚至数百MB
- 删除大key时引起Redis阻塞（DEL大对象是O(N)操作）

**处理方案**:
1. **拆分大Key**: 将大的 Hash 拆分为多个小的 Hash
2. **数据压缩**: 使用 snappy/lz4 压缩后再存入
3. **改用其他存储**: 超大数据改用 SSD Redis 或对象存储
4. **安全删除**: 使用 UNLINK 异步删除替代 DEL
5. **分批删除**: Hash 用 HDEL 逐个删除，Set 用 SREM + SSCAN

### 原因2: Key 过期策略失效
**特征**:
- keyspace 中 key 数量持续增长
- expired_keys 数量少但 evicted_keys 数量多
- 没有设置过期时间的 key 大量存在

**处理方案**:
1. 所有缓存 Key 必须设置 TTL（过期时间）
2. 合理配置 maxmemory-policy（推荐 allkeys-lru 或 volatile-lru）
3. 避免大批量 key 在同一时间过期（加随机偏移）
4. 定期巡检无 TTL 的 Key

### 原因3: 内存碎片严重
**特征**:
- mem_fragmentation_ratio > 1.5
- used_memory_rss 远大于 used_memory
- 频繁增删 Key 导致碎片

**处理方案**:
1. 启用 `activedefrag yes`（Redis 4.0+ 自动碎片整理）
2. 手动执行 `MEMORY PURGE`
3. 使用 jemalloc 内存分配器
4. 重启 Redis 彻底清理碎片（需主从切换）

### 原因4: 写入流量突增
**特征**:
- 业务高峰期内存快速上涨
- 瞬时写入量远超正常水平
- 无大Key但整体key数量暴增

**处理方案**:
1. 应用层限流，控制写入速率
2. 临时扩容（增加内存或分片）
3. 缩短过期时间，加速淘汰
4. 非核心数据降级写入（异步队列）

### 原因5: 缓存穿透/击穿
**特征**:
- 大量不存在的 Key 被查询
- 空值未缓存导致每次请求都穿透到数据库
- 热点 Key 过期瞬间大量请求打到数据库

**处理方案**:
1. **缓存空值**: 对不存在的数据也缓存（短期TTL）
2. **布隆过滤器**: 使用 RedisBloom 模块过滤不存在的Key
3. **互斥锁**: 热点Key过期时，只有一个线程去加载数据
4. **永不过期**: 热点Key物理不过期，后台异步更新值

### 原因6: 客户端连接泄露
**特征**:
- connected_clients 数量持续增长
- 大量 idle 连接未释放
- 新连接被拒绝（maxclients 达到上限）

**处理方案**:
1. 应用端连接池配置 timeout 参数
2. 设置 Redis `timeout 300` 自动关闭空闲连接
3. 检查应用代码确保连接正确关闭
4. 增加 maxclients 配置

## 紧急处理措施

### 立即操作（5分钟内）
1. **扩容**: 如果 Redis Cluster，增加分片节点
2. **清理**: 删除明确无用的大Key（用 UNLINK）
3. **限流**: 应用层限流减少写入
4. **调整策略**: `CONFIG SET maxmemory-policy allkeys-lru` 加速淘汰

### 短期措施（30分钟内）
1. 分析大Key并制定拆分方案
2. 调整过期时间和淘汰策略
3. 检查客户端连接池配置
4. 增加内存告警阈值监控

### 长期优化
1. 定期大Key巡检和清理
2. 建立Key命名规范和TTL规范
3. 部署 Redis Cluster 实现水平扩展
4. 冷热数据分离（热数据Redis，冷数据SSD Redis）
5. 监控面板：内存趋势、命中率、连接数、慢查询

## 监控指标
- **内存使用率**: used_memory / maxmemory
- **内存碎片率**: mem_fragmentation_ratio
- **缓存命中率**: keyspace_hits / (keyspace_hits + keyspace_misses)
- **过期Key速率**: expired_keys / sec
- **驱逐Key速率**: evicted_keys / sec
- **连接数**: connected_clients / maxclients
- **慢查询**: slowlog 记录数

## 相关告警
- `RedisConnectionFailed`: Redis 连接失败
- `RedisSlowLog`: Redis 慢查询
- `CacheHitRateLow`: 缓存命中率过低
- `DatabaseCPUHigh`: 缓存失效导致数据库压力增大

## 联系方式
- **DBA/中间件团队**: middleware-team@company.com
- **紧急电话**: 400-xxx-4444
