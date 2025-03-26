class DotDict:
    """
    Wrapper class for accessing dictionary keys as attributes
    """

    def __init__(self, data):
        self.data = data

    def __getattr__(self, key):
        return self.data.get(key)