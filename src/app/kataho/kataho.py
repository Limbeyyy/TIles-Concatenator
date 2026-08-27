import asyncio

import kataho.core.kataho_converters as KatahoConverters
from kataho.core.kataho_models import KSuggestionModel

class KatahoSDK:
    @staticmethod
    def kataho_to_plus(kataho_code: str):
        return KatahoConverters.convert_from_kataho_code_to_plus_code(kataho_code)
    
    @staticmethod
    def plus_to_kataho(plus_code: str, is_nepali: bool = True) -> str:
        return KatahoConverters.convert_from_plus_code_to_Kataho_code(plus_code, is_nepali)
    
    @staticmethod
    def kataho_to_lat_lng(kataho_code: str) -> str:
        return KatahoConverters.convert_from_plus_code_to_lat_lng(
            KatahoConverters.convert_from_kataho_code_to_plus_code(kataho_code)
        )
    
    @staticmethod
    def lat_lng_to_kataho(lat_lng: str, is_nepali:bool = True) -> str:
        return KatahoConverters.convert_from_plus_code_to_Kataho_code(
            KatahoConverters.convert_from_lat_lng_to_plus_code(lat_lng), is_nepali
        )
        
    
    @staticmethod
    def plus_to_lat_lng(plus_code: str) -> str:
        return KatahoConverters.convert_from_plus_code_to_lat_lng(plus_code)
    
    @staticmethod
    def lat_lng_to_plus(lat_lng: str) -> str:
        return KatahoConverters.convert_from_lat_lng_to_plus_code(lat_lng)
    
    @staticmethod
    def get_id_from_main_word(main_word: str) -> int:
        return KatahoConverters.get_id_from_main_word(main_word)
    
    @staticmethod
    def get_main_word_from_id(main_word_id: int):
        return KatahoConverters.get_main_word_from_id(main_word_id)

    @staticmethod
    async def suggestions(query) -> list[KSuggestionModel]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, KatahoConverters.generate_kataho_words_suggestions_from_query, query)