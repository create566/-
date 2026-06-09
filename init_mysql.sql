-- ============================================================
-- 智能监控平台 — MySQL 初始化脚本
-- 使用方式: mysql -u root -p < init_mysql.sql
-- ============================================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS smart_monitor
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE smart_monitor;

-- -----------------------------------------------------------
-- 1. 被监控系统
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS systems (
    id                  VARCHAR(64)   NOT NULL PRIMARY KEY COMMENT '系统唯一标识',
    name                VARCHAR(128)  NOT NULL                COMMENT '系统名称',
    system_type         VARCHAR(32)   DEFAULT 'web_service' COMMENT '系统类型',
    status              VARCHAR(16)   DEFAULT 'active'      COMMENT '状态: active/inactive/paused',
    endpoint            VARCHAR(512)  DEFAULT ''             COMMENT '监控端点URL',
    auth                JSON          NULL                   COMMENT '认证信息',
    detectors           JSON          NULL                   COMMENT '启用的检测器列表',
    check_interval_seconds INT        DEFAULT 60             COMMENT '检测间隔(秒)',
    alert_enabled       TINYINT(1)    DEFAULT 1             COMMENT '是否启用告警',
    health_score        INT           DEFAULT 100            COMMENT '健康评分 0-100',
    last_checked_at     DATETIME      NULL                   COMMENT '最后检测时间',
    created_at          DATETIME      DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at          DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='被监控系统表';

-- -----------------------------------------------------------
-- 2. 故障/告警记录
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents (
    id                  VARCHAR(64)   NOT NULL PRIMARY KEY COMMENT '故障唯一ID',
    system_id           VARCHAR(64)   NOT NULL                COMMENT '关联系统ID',
    system_name         VARCHAR(128)  NULL                   COMMENT '系统名称(冗余)',
    severity            VARCHAR(16)   NOT NULL               COMMENT '严重级别: critical/warning/info',
    status              VARCHAR(16)   DEFAULT 'open'         COMMENT '状态: open/acknowledged/resolved',
    title               VARCHAR(256)  NOT NULL               COMMENT '故障标题',
    message             TEXT          NULL                   COMMENT '故障描述',
    root_cause          TEXT          NULL                   COMMENT '根因分析',
    report              TEXT          NULL                   COMMENT '诊断报告',
    anomalies           JSON          NULL                   COMMENT '异常指标详情',
    created_at          DATETIME      DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    acknowledged_at     DATETIME      NULL                   COMMENT '确认时间',
    resolved_at         DATETIME      NULL                   COMMENT '解决时间',
    INDEX idx_system_id (system_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='故障记录表';

-- -----------------------------------------------------------
-- 3. 检测历史
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS check_history (
    id                  INT           NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
    system_id           VARCHAR(64)   NOT NULL                COMMENT '系统ID',
    detector_name       VARCHAR(64)   NOT NULL               COMMENT '检测器名称',
    metric_name         VARCHAR(64)   NOT NULL               COMMENT '指标名称',
    metric_value        DOUBLE        NULL                   COMMENT '指标值',
    severity            VARCHAR(16)   DEFAULT 'normal'       COMMENT '严重级别',
    checked_at          DATETIME      DEFAULT CURRENT_TIMESTAMP COMMENT '检测时间',
    INDEX idx_system_id (system_id),
    INDEX idx_checked_at (checked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='检测历史表';

-- -----------------------------------------------------------
-- 4. AI 助手会话
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_sessions (
    id                  VARCHAR(64)   NOT NULL PRIMARY KEY COMMENT '会话唯一ID',
    chat_source         VARCHAR(16)   NOT NULL DEFAULT 'web' COMMENT '来源: web/feishu',
    source_id           VARCHAR(128)  NOT NULL               COMMENT '来源用户标识',
    title               VARCHAR(256)  DEFAULT ''             COMMENT '会话标题',
    created_at          DATETIME      DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at          DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_source_id (source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='聊天会话表';

-- -----------------------------------------------------------
-- 5. 聊天消息
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_messages (
    id                  INT           NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
    session_id          VARCHAR(64)   NOT NULL               COMMENT '会话ID',
    role                VARCHAR(16)   NOT NULL               COMMENT '角色: user/assistant/system',
    content             TEXT          NOT NULL               COMMENT '消息内容',
    created_at          DATETIME      DEFAULT CURRENT_TIMESTAMP COMMENT '发送时间',
    INDEX idx_session_id (session_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='聊天消息表';

-- -----------------------------------------------------------
-- 6. 用户偏好/记忆
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_facts (
    id                  INT           NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
    session_id          VARCHAR(64)   NOT NULL               COMMENT '会话ID',
    `key`               VARCHAR(256)  NOT NULL               COMMENT '事实键',
    `value`             TEXT          NOT NULL               COMMENT '事实值',
    category            VARCHAR(64)   DEFAULT 'general'      COMMENT '分类',
    created_at          DATETIME      DEFAULT CURRENT_TIMESTAMP COMMENT '创建/更新时间',
    INDEX idx_session_id (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='记忆事实表';
