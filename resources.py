import logging
import weakref
import atexit

class ResourceTracker:
    """资源追踪器（确保程序退出时清理所有资源）"""
    
    def __init__(self):
        self.resources = weakref.WeakSet()
        self.logger = logging.getLogger(__name__)
        atexit.register(self.cleanup_all)
    
    def register(self, resource, name=None):
        """注册需要清理的资源"""
        self.resources.add(resource)
        resource_name = name or type(resource).__name__
        self.logger.debug(f"注册资源: {resource_name}")
    
    def cleanup_all(self):
        """清理所有已注册的资源"""
        self.logger.info("开始清理所有资源...")
        cleaned = 0
        
        for resource in list(self.resources):
            try:
                resource_name = type(resource).__name__
                
                # 根据资源类型调用相应的清理方法
                if hasattr(resource, 'close'):
                    resource.close()
                    self.logger.debug(f"关闭资源: {resource_name}")
                elif hasattr(resource, 'stop'):
                    resource.stop()
                    self.logger.debug(f"停止资源: {resource_name}")
                elif hasattr(resource, 'shutdown'):
                    resource.shutdown()
                    self.logger.debug(f"关闭资源: {resource_name}")
                
                cleaned += 1
            except Exception as e:
                self.logger.error(f"清理资源失败: {e}")
        
        self.logger.info(f"资源清理完成，共清理{cleaned}个资源")
# 全局资源追踪器
resource_tracker = ResourceTracker()
