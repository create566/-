# MySQL 慢查询故障处理方案

## 告警名称
- **告警名**: `MySQLSlowQuery`
- **告警级别**: 警告 / 严重
- **触发条件**: 慢查询数量超过阈值（警告≥10，严重≥50）

## 问题描述
当 MySQL 慢查询数量持续增加时，会导致：
- 数据库连接池耗尽，新请求无法获取连接
- 应用线程阻塞等待数据库响应
- CPU 使用率攀升（数据库服务器和应用服务器）
- API 响应时间延长，超时率上升
- 级联故障：慢查询 → 连接池满 → API超时 → 上游服务降级

## 排查步骤

### 步骤1: 确认慢查询规模
```sql
SHOW GLOBAL STATUS LIKE 'Slow_queries';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'slow_query_log';
```

### 步骤2: 找出最慢的SQL
```sql
-- MySQL 5.7+
SELECT * FROM mysql.slow_log ORDER BY query_time DESC LIMIT 10;

-- 或查看慢查询日志文件
```

### 步骤3: 分析执行计划
```sql
EXPLAIN SELECT ...;        -- 查看执行计划
EXPLAIN FORMAT=JSON SELECT ...;  -- 详细JSON格式
SHOW PROFILES;             -- 查看实际资源消耗
```

### 步骤4: 检查索引使用情况
```sql
-- 查看未使用索引
SELECT * FROM sys.schema_unused_indexes;
-- 查看冗余索引
SELECT * FROM sys.schema_redundant_indexes;
-- 查看全表扫描的表
SELECT * FROM sys.schema_tables_with_full_table_scans;
```

### 步骤5: 检查锁竞争
```sql
SHOW ENGINE INNODB STATUS\G
SELECT * FROM information_schema.INNODB_TRX;
SELECT * FROM information_schema.INNODB_LOCKS;
SELECT * FROM information_schema.INNODB_LOCK_WAITS;
```

## 常见原因分析

### 原因1: 缺少索引导致全表扫描
**特征**:
- EXPLAIN 显示 type=ALL（全表扫描）
- rows 数量巨大
- 表数据量大但未建索引

**处理方案**:
1. 使用 EXPLAIN 分析慢查询SQL
2. 为 WHERE/JOIN/ORDER BY 字段添加合适索引
3. 考虑复合索引的最左前缀原则
4. 避免在索引列上使用函数或计算
5. 定期更新表统计信息：`ANALYZE TABLE`

### 原因2: SQL 写法低效
**特征**:
- SELECT * 查询大量无用字段
- 子查询未优化
- JOIN 过多或未正确使用
- OR 条件导致索引失效

**处理方案**:
1. 只查询需要的字段，避免 SELECT *
2. 将子查询改写为 JOIN
3. 使用覆盖索引避免回表
4. 将 OR 改写为 UNION ALL
5. 大表分页使用游标而非 OFFSET

### 原因3: 锁竞争与死锁
**特征**:
- 事务等待时间长
- 出现死锁日志
- UPDATE/DELETE 大量数据未分批

**处理方案**:
1. 大事务拆分为小事务
2. 合理设置事务隔离级别
3. 避免在事务中执行耗时操作
4. 按相同顺序访问表，避免死锁

### 原因4: 数据量增长导致性能下降
**特征**:
- 历史数据未归档
- 单表数据量过亿
- 索引B+树层级过深

**处理方案**:
1. 实施数据归档策略（按月/年分区）
2. 使用分区表（PARTITION BY RANGE）
3. 考虑分库分表（Sharding）
4. 冷热数据分离存储

### 原因5: 连接池配置不当
**特征**:
- 连接数经常接近最大值
- 出现 "Too many connections" 错误
- 大量连接处于 Sleep 状态

**处理方案**:
1. 合理设置 max_connections
2. 应用端配置连接池（最大连接数、超时时间）
3. 确保连接使用后及时释放
4. 设置 wait_timeout 回收空闲连接

## 紧急处理措施

### 立即操作（5分钟内）
1. **杀死慢查询**: `KILL <thread_id>` 终止特别慢的查询
2. **限流**: 限制并发连接数 `SET GLOBAL max_connections = 200`
3. **强制索引**: `SELECT /*+ INDEX(table idx_name) */ ...`

### 短期措施（30分钟内）
1. 添加缺失索引
2. 优化TOP 5慢SQL
3. 增加连接池大小（临时缓解）
4. 开启查询缓存（如果适用）

### 长期优化
1. 定期慢查询审计
2. SQL审核流程（上线前review）
3. 读写分离 / 分库分表
4. 引入缓存层（Redis）降低数据库压力

## 监控指标
- **慢查询数量**: 每分钟新增慢查询数
- **连接数**: 当前连接数 / 最大连接数
- **QPS/TPS**: 查询和事务吞吐量
- **查询响应时间**: P50/P90/P99
- **InnoDB缓冲池命中率**: 应 ≥ 99%

## 相关告警
- `HighCPUUsage`: 数据库服务器CPU高
- `HighMemoryUsage`: 数据库内存使用高
- `DiskIOHigh`: 磁盘IO高（大量读写）
- `ConnectionPoolFull`: 连接池满载

## 联系方式
- **DBA团队**: dba-team@company.com
- **紧急电话**: 400-xxx-3333
