class Item(object):
    """
    An item a character can hold in their inventory. Describes names,
    type IDs, reprocessing outputs, etc. Does _not_ hold any kind
    of pricing or valuation information - those are offers and are
    not a property of an item.
    """
    def __init__(self, enUsName, typeId, portionSize):
        self.typeId = typeId
        self.name = enUsName
        self.portionSize = portionSize
        self.reprocessingOutputs = {}

    def addReprocessingOutputs(self, outputTypeId, outputQuantity):
        self.reprocessingOutputs[outputTypeId] = outputQuantity

