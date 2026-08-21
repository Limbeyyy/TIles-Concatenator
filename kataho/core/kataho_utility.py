import os
import re
from datetime import datetime
from kataho.core.kataho_codes import KatahoCodes
from kataho.core.kataho_models import KLatLng

LOG_PATH = './logs/logs.log'

def kataho_log(text:str, timestamp:bool=True):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    # filename -> '/YYYY-MM-DD-error.log'
    # filename = '/' + str(datetime.now().date()) + '-' + 'error.log'
    with open(LOG_PATH, 'a') as log_file:
        text = f"{datetime.now()} {text}" if timestamp else text
        print(text, file=log_file)

def is_entered_kataho_nepali_words_valid(kataho_words: str):
    if not kataho_words:
        return True

    words = kataho_words.split(" ")
    n_words = len(words)

    if n_words < 1 or n_words > 4:
        return False
    
    prefix_verification = lambda element: element.nepaliCode.startswith(words[0]) or not words[0] if n_words == 1 else element.nepaliCode == words[0]
    prefixIsValid = any(prefix_verification(element) for element in KatahoCodes.prefix_number_model_list)

    second_word_verification = lambda element: element.nepaliCode.startswith(words[1]) or not words[1] \
        if n_words == 2 else element.nepaliCode == words[1] \
        if n_words > 1 else True
    secondWordIsValid = any(second_word_verification(element) for element in KatahoCodes.main_word_model_list)

    third_word_verification = lambda element: element.nepaliCode.startswith(words[2]) or not words[2] \
        if n_words == 3 else element.nepaliCode == words[2] \
        if n_words > 2 else True
    thirdWordIsValid = any(third_word_verification(element) for element in KatahoCodes.main_word_model_list)

    suffix_verification = lambda element: element.nepaliCode.startswith(words[3]) or not words[3] \
        if n_words == 4 else element.nepaliCode == words[3] \
        if n_words == 4 else True
    suffixIsValid = any(suffix_verification(element) for element in KatahoCodes.suffix_number_model_list)

    return all([prefixIsValid, secondWordIsValid, thirdWordIsValid, suffixIsValid])

def is_entering_kataho_nepali_or_rnglish_words_valid(kataho_words: str):
    if not kataho_words:
        return True

    words = kataho_words.split(" ")
    n_words = len(words)

    if n_words < 1 or n_words > 4:
        return False
    
    prefix_verification = lambda element: element.nepaliCode.startswith(words[0]) or element.romanCode.startswith(words[0]) or not words[0] \
        if n_words == 1 else element.nepaliCode == words[0]
    prefixIsValid = any(prefix_verification(element) for element in KatahoCodes.prefix_number_model_list)

    second_word_verification = lambda element: element.nepaliCode.startswith(words[1]) or element.romanCode.startswith(words[1]) or not words[1] \
        if n_words == 2 else element.nepaliCode == words[1] \
        if n_words > 1 else True
    secondWordIsValid = any(second_word_verification(element) for element in KatahoCodes.main_word_model_list)

    third_word_verification = lambda element: element.nepaliCode.startswith(words[2]) or element.romanCode.startswith(words[2]) or not words[2] \
        if n_words == 3 else element.nepaliCode == words[2] \
        if n_words > 2 else True
    thirdWordIsValid = any(third_word_verification(element) for element in KatahoCodes.main_word_model_list)

    suffix_verification = lambda element: element.nepaliCode.startswith(words[3]) or element.romanCode.startswith(words[3]) or not words[3] \
        if n_words == 4 else element.nepaliCode == words[3] \
        if n_words == 4 else True
    suffixIsValid = any(suffix_verification(element) for element in KatahoCodes.suffix_number_model_list)

    return all([prefixIsValid, secondWordIsValid, thirdWordIsValid, suffixIsValid])

def is_kataho_code_valid(kataho_code: str):
    if not kataho_code: return False 

    words = kataho_code.split(" ")
    if len(words) < 4: return False

    prefix_verification = lambda element: element.nepaliCode == words[0]
    prefixIsValid = any(prefix_verification(element) for element in KatahoCodes.prefix_number_model_list)

    second_word_verification = lambda element: element.nepaliCode == words[1]
    secondWordIsValid = any(second_word_verification(element) for element in KatahoCodes.main_word_model_list)

    third_word_verification = lambda element: element.nepaliCode == words[2]
    thirdWordIsValid = any(third_word_verification(element) for element in KatahoCodes.main_word_model_list)

    suffix_verification = lambda element: element.nepaliCode == words[3]
    suffixIsValid = any(suffix_verification(element) for element in KatahoCodes.suffix_number_model_list)

    return all([prefixIsValid, secondWordIsValid, thirdWordIsValid, suffixIsValid])

def is_plus_code_valid(code: str):
    pattern = re.compile(r"[23456789CFGHJMPQRVWX\+]{4}\+[23456789CFGHJMPQRVWX\+]{3}")
    return bool(pattern.search(code))

def is_lat_lng_valid(latlng: str):
    pattern = re.compile(r"(-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?)")
    return bool(pattern.search(latlng))

def is_digit_in_unicode_nepali(text: str):
    return any(c.isdigit() for c in text)

def toKLatLng(string):
    latlng_str = string.split(',')
    return KLatLng(
        float(latlng_str[0]) if latlng_str[0] else 0.0,
        float(latlng_str[1]) if latlng_str[1] else 0.0
    )
