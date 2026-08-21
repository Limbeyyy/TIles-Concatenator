"""
    Model class for kataho project.
"""

from abc import ABC, abstractmethod


class KBaseModel(ABC):
    '''Base class for Kataho Model Classes'''
    @abstractmethod
    def to_pretty_string(self):
        pass


class KCodeModel(KBaseModel):
    def __init__(self, plusCode, nepaliCode, romanCode, romanCode2) -> None:
        self.plusCode = plusCode
        self.nepaliCode = nepaliCode
        self.romanCode = romanCode
        self.romanCode2 = romanCode2

    def to_pretty_string(self):
        return f"""
            Plus Code: {self.plusCode}, Nepali Kataho Code: {self.nepaliCode}, Roman Kataho Code: {self.romanCode}, Roman Kataho Code 2 (Hint): {self.romanCode2}        
        """

class KSuggestionModel(KBaseModel):
    def __init__(self, nepali, roman) -> None:
        self.nepali = nepali
        self.roman = roman

    def to_pretty_string(self):
        return f"Nepali: {self.nepali}, Roman: {self.roman}"
        
class KLatLng(KBaseModel):
    def __init__(self, latitude, longitude) -> None:
        self.latitude = latitude
        self.longitude = longitude

    def to_comma_sting(self):
        return f"{self.latitude},{self.longitude}"
    
    def to_pretty_string(self):
        return f"Latitude: {self.latitude}, Longitude: {self.longitude}"
    

        
