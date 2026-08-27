class Consolidator:
    def __init__(self):
        self.datasets = {}

    def add(self, name, data):
        self.datasets[name] = data

    def consolidate(self):
        consolidated = {}
        for name, data in self.datasets.items():
            consolidated[name] = data
        self.consolidated = consolidated
        return consolidated
