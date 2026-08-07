from abc import ABC, abstractmethod

class DatabaseAPI(ABC):
    def __init__(self):
        pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

    @abstractmethod
    def start(self):
        pass
    
    @abstractmethod
    def shutdown(self):
        pass

    @abstractmethod
    def clear(self):
        pass