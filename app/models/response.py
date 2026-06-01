"""响应数据模型

定义 API 响应的 Pydantic 模型
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Generic, TypeVar


class UnifiedResponse(BaseModel, Generic[TypeVar("T")]):
    """统一响应格式

    所有 API 统一返回格式:
    {
        "code": 200,
        "message": "success",
        "data": {
            "success": true,
            "result": "实际结果",
            "errorMessage": null
        }
    }
    """

    code: int = Field(200, description="状态码，200表示成功")
    message: str = Field("success", description="状态信息")
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="数据内容，固定包含 success, result, errorMessage 三个字段"
    )

    @classmethod
    def success(cls, result: Any = None, message: str = "success"):
        """构建成功响应"""
        return cls(
            code=200,
            message=message,
            data={
                "success": True,
                "result": result,
                "errorMessage": None
            }
        )

    @classmethod
    def error(cls, error_message: str, code: int = 500):
        """构建错误响应"""
        return cls(
            code=code,
            message="error",
            data={
                "success": False,
                "result": None,
                "errorMessage": error_message
            }
        )


class ChatResponse(BaseModel):
    """对话响应"""

    answer: str = Field(..., description="AI 回答")
    session_id: str = Field(..., description="会话 ID")


class SessionInfoResponse(BaseModel):
    """会话信息响应"""

    session_id: str = Field(..., description="会话 ID")
    message_count: int = Field(..., description="消息数量")
    history: List[Dict[str, str]] = Field(..., description="历史消息列表")


class ApiResponse(BaseModel):
    """通用 API 响应"""

    status: str = Field(..., description="状态")
    message: str = Field(..., description="消息")
    data: Optional[Any] = Field(None, description="数据")


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str = Field(..., description="状态")
    service: str = Field(..., description="服务名称")
    version: str = Field(..., description="版本号")
