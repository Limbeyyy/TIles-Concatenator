from kataho.core.kataho_codes import KatahoCodes
from kataho.core.kataho_models import KCodeModel, KSuggestionModel
from kataho.core.kataho_utility import kataho_log
from kataho.core.kataho_olc import CodeArea, encode, decode


# class KatahoConverters:
def get_kataho_number_from_plus_code_after_plus(plus_code_after_plus: str, is_nepali: bool):
    for code_model in KatahoCodes.suffix_number_model_list:
        if code_model.plusCode == plus_code_after_plus:
            return code_model.nepaliCode if is_nepali else code_model.romanCode
    return ""

def get_plus_code_after_plus_from_kataho_number(kataho_number_four_digit:str):
    for code_model in KatahoCodes.suffix_number_model_list:
        if (code_model.nepaliCode == kataho_number_four_digit or 
            code_model.romanCode == kataho_number_four_digit):
            return code_model.plusCode
    return ""

def get_plus_code_from_prefix_number(prefix_number: str):
    for code_model in KatahoCodes.prefix_number_model_list:
        if (code_model.nepaliCode == prefix_number or 
            code_model.romanCode == prefix_number):
            return code_model.plusCode
    return ""

def get_plus_code_from_main_word(main_word: str):
    for code_model in KatahoCodes.main_word_model_list:
        if (code_model.nepaliCode == main_word or 
            code_model.romanCode == main_word):
            return code_model.plusCode
    return ""

def get_prefix_number_from_plus_code(plus_code: str, is_nepali: bool):
    for code_model in KatahoCodes.prefix_number_model_list:
        if code_model.plusCode == plus_code:
            return code_model.nepaliCode if is_nepali else code_model.romanCode
    return ""

def get_main_word_from_plus_code(plus_code: str, is_nepali: bool):
    for code_model in KatahoCodes.main_word_model_list:
        if code_model.plusCode == plus_code:
            return code_model.nepaliCode if is_nepali else code_model.romanCode
    return ""

def get_main_word_from_id(main_word_id: int):
    if main_word_id < 0 or main_word_id >= len(KatahoCodes.main_word_model_list):
        return ""
    return KatahoCodes.main_word_model_list[main_word_id-1].nepaliCode

def get_id_from_main_word(main_word_nepali: str):
    if not main_word_nepali: return 0
    for i in range(len(KatahoCodes.main_word_model_list)):
        if KatahoCodes.main_word_model_list[i].nepaliCode == main_word_nepali:
            return i+1
    return 0

# main entry point
def convert_from_kataho_code_to_plus_code(kataho_code: str):
    plus_code: str = "7M"

    try:
        kataho_code_split: list[str] = kataho_code.split(" ")
        for i in range(4):
            item: str = kataho_code_split[i]
            match i:
                case 0:
                    plus_code += get_plus_code_from_prefix_number(item)
                case 1:
                    plus_code += get_plus_code_from_main_word(item)
                case 2:
                    plus_code += get_plus_code_from_main_word(item)
                case 3:
                    plus_code += f"+{get_plus_code_after_plus_from_kataho_number(item)}"
    except Exception as e:
        kataho_log(str(e))

    return plus_code

def convert_from_plus_code_to_Kataho_code(plus_code: str, is_nepali: bool):
    kataho_code: str = ""
    plus_code = plus_code.replace("7M", "", 1)

    try:
        plus_code_split: list[str] = plus_code.split("+")
        before_plus, after_plus = plus_code_split[0], plus_code_split[1]

        # Split 'beforePlus' into every two characters
        split_before_plus_list = [before_plus[i:i+2] for i in range(0, len(before_plus), 2)]

        # klog("convertFromPlusCodeToKatahoCode PlusCode: $plusCode | $beforePlus | $afterPlus | ${splitBeforePlusList.toString()}")
        # katahoCode += " " + beforePlus + " | " + splitBeforePlusList[0] + " " + splitBeforePlusList[1] + " " + splitBeforePlusList[2]
        for i in range(0, 3, 1):
            item: str = split_before_plus_list[i]

            if i == 0:
                kataho_code += get_prefix_number_from_plus_code(item, is_nepali)
            elif i == 1 or i == 2:
                kataho_code += f" {get_main_word_from_plus_code(item, is_nepali)}"
        kataho_code += f" {get_kataho_number_from_plus_code_after_plus(after_plus, is_nepali)}"
    except Exception as e:
        kataho_log(str(e))

    return kataho_code

def convert_from_plus_code_to_lat_lng(plus_code: str):
    center: CodeArea = decode(plus_code)
    c_lat, c_long = center.latlng()
    return f"{c_lat},{c_long}"

def convert_from_lat_lng_to_plus_code(latlng:str):
    latlng_parts = latlng.split(",")
    try:
        return encode(float(latlng_parts[0]) or 0.0, float(latlng_parts[1]) or 0.0)
    except Exception as e:
        kataho_log(str(e))
        return encode(0.0, 0.0)
        
# Kataho suggestion from Query
def get_kataho_word_suggestion_from_code_model_list(
        code_model_list: list[KCodeModel],
        query: str
):
    suggestion_list: list[KSuggestionModel] = []
    max_size: int = 50 if len(code_model_list) > 50 else len(code_model_list)

    if not query:
        for i in range(max_size):
            model: KCodeModel = code_model_list[i]
            suggestion_list.append(KSuggestionModel(model.nepaliCode, model.romanCode))
    else:
        query_lower_case = query.lower()

        count: int = 0
        for model in code_model_list:
            if (query in model.nepaliCode or
                query_lower_case in model.romanCode.lower()):
                suggestion_list.append(KSuggestionModel(model.nepaliCode, model.romanCode))
                count += 1
            if count == max_size:
                break
        suggestion_list.sort(key=lambda x: 0 if x.nepali.startswith(query) or x.roman.startswith(query) else 1)
        # suggestion_list.sort(key=lambda x: (x['nepali'].startswith(query) or x['roman'].startswith(query), x))
    
    return suggestion_list

def generate_kataho_words_suggestions_from_query(query: str):
    kataho_words_suggestions: list[KSuggestionModel] = []
    
    is_query_empty: bool = not query
    is_query_ends_with_space: bool = query.endswith(' ')

    # validate and parse query
    query_words: list[str] = query.split(' ')
    query_size: int = len(query_words)

    if is_query_empty or is_query_ends_with_space:
        # Add an empty item to the queryWords vector
        query_words.append("")

    if query_size == 1:
        # Get suggestions from prefix number
        kataho_words_suggestions = get_kataho_word_suggestion_from_code_model_list(
            KatahoCodes.prefix_number_model_list, query_words[0]
        )
    elif query_size == 2:
        # Get suggestions from Main word
        kataho_words_suggestions = get_kataho_word_suggestion_from_code_model_list(
            KatahoCodes.main_word_model_list, query_words[1]
        )
    elif query_size == 3:
        # Get suggestions from Main word
        kataho_words_suggestions = get_kataho_word_suggestion_from_code_model_list(
            KatahoCodes.main_word_model_list, query_words[2]
        )
    elif query_size == 4:
        # Get suggestions from suffix
        kataho_words_suggestions = get_kataho_word_suggestion_from_code_model_list(
            KatahoCodes.suffix_number_model_list, query_words[3]
        )
    
    return kataho_words_suggestions
