import re
import requests
import pandas as pd
from .athlet import Athlet

WIKIMEDIA_ID_FORMAT = r"^Q\d+$"
WIKIDATA_URL = "https://query.wikidata.org/sparql"
WIKIDATA_COLUMNS = {
    'person.value': "person",
    'personLabel.value': "label",
    'dateOfBirth.value': "birth",
    'dateOfDeath.value': "death",
    'genderLabel.value': "gender",
    'countryOfCitizenshipLabel.value': "citizienship",
    'occupationLabel.value': "occupation",
}


def get_athlet(input, alive=True, lang="it", only_deads=False) -> list[Athlet]:
    athlets = []

    df = get_athlet_info(input, lang, only_deads=only_deads)
    if df.empty:
        return athlets

    if alive:
        df = df[df["death"] == ''].sort_values(by=["birth"]).reset_index(drop=True)

    for _, athlet in df.iterrows():
        p = Athlet(
            name=athlet.label,
            dob=athlet.birth,
            dod=athlet.death if athlet.death else None,
            WID=athlet.person.split("/")[-1],
            citizienships=[c for c in athlet.citizienship if c],
            genders=[g for g in athlet.gender if g],
            occupations=[o for o in athlet.occupation if o],
        )
        athlets.append(p)
    return athlets


def update_athlets(ids: list, lang="it") -> list[Athlet]:
    # updated_athlets = {}
    # for id, pers in dict_athlets.items():
    #     updated_pers = get_athlet(id, alive=False, lang=lang, only_deads=True)
    #     if (pers.dod != updated_pers.dod or
    #        pers.genders != updated_pers.genders or
    #        pers.citizenships != updated_pers.citizenships or
    #        pers.occupations != updated_pers.occupations):
    #         updated_athlets[id] = updated_pers
    updated_athlets = get_athlet(ids, alive=False, lang=lang, only_deads=True)
    return updated_athlets
 

def get_athlet_info(input: str, lang: str, only_deads: bool = False) -> pd.DataFrame:
    if type(input) is list:
        query = get_query_from_multi_ids(ids=input, lang=lang, only_deads=only_deads)
    elif re.match(WIKIMEDIA_ID_FORMAT, input):
        query = get_query_from_id(id=input, lang=lang)
    else:
        query = get_query_from_name(name=input, lang=lang)
    # Set the headers and parameters for the request
    # headers = {
    #     'Content-Type': 'application/x-www-form-urlencoded',
    # }
    params = {
        'format': 'json',
        'query': query
    }

    # Send the request and get the response
    response = requests.get(WIKIDATA_URL, params=params)
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the response as JSON
        data = response.json()

        df = get_query_df(data)

        # if not is_unique_athlet(df):
        #     raise ValueError("Too many results, try to directly send the Wikimedia ID")
     
        return df
    else:
        # The request was not successful, so return None
        raise requests.ConnectionError(f"Wikidata problem. Response status code: {response.status_code}")


def get_query_df(data):
    df = pd.json_normalize(data["results"]["bindings"])
    if df.empty:
        return df
    discarded_columns = [c for c in df.columns if c not in WIKIDATA_COLUMNS]
    missing_columns = [c for c in WIKIDATA_COLUMNS if c not in df.columns]
    df.drop(labels=discarded_columns, axis=1, inplace=True)
    df[missing_columns] = ''
    df.fillna('', inplace=True)
    df.rename(columns=WIKIDATA_COLUMNS, inplace=True)
    grouped = df.groupby(["person", "birth", "label", "death"]).agg(lambda x: sorted(list(set(x)))).reset_index()
    with_dob = grouped[grouped["birth"] != ""].reset_index(drop=True)
    return with_dob


def is_unique_athlet(df):
    if len(df["person"].unique()) == 1:
        return True
    else:
        return False


def get_query_from_id(id, lang):
    return """
    SELECT ?person ?personLabel ?dateOfBirth ?dateOfDeath ?genderLabel ?countryOfCitizenshipLabel ?occupationLabel
    WHERE
    {{
      ?person wdt:P31 wd:Q5 .  # ?person is a human
      ?person wdt:P569 ?dateOfBirth .  # ?person has a date of birth
      OPTIONAL {{ ?person wdt:P570 ?dateOfDeath . }}  # ?person has a date of death (optional)
      OPTIONAL {{ ?person wdt:P21 ?gender . }}  # ?person has a gender (optional)
      OPTIONAL {{ ?person wdt:P27 ?countryOfCitizenship . }}  # ?person has a country of citizenship (optional)
      OPTIONAL {{ ?person wdt:P106 ?occupation . }}  # ?person has an occupation (optional)
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{},en". }}
      FILTER (?person = wd:{})  # QID is the Wikidata identifier for the person
    }}
    """.format(lang, id)

def get_query_from_multi_ids(ids, lang, only_deads=False):
    ids = [f"wd:{id}" for id in ids]
    ids_txt = ", ".join(ids)
    if only_deads:
        return """
        SELECT ?person ?personLabel ?dateOfBirth ?dateOfDeath ?genderLabel ?countryOfCitizenshipLabel ?occupationLabel
        WHERE
        {{
        ?person wdt:P31 wd:Q5 .  # ?person is a human
        ?person wdt:P569 ?dateOfBirth .  # ?person has a date of birth
        ?person wdt:P570 ?dateOfDeath .  # ?person has a date of death (optional)
        OPTIONAL {{ ?person wdt:P21 ?gender . }}  # ?person has a gender (optional)
        OPTIONAL {{ ?person wdt:P27 ?countryOfCitizenship . }}  # ?person has a country of citizenship (optional)
        OPTIONAL {{ ?person wdt:P106 ?occupation . }}  # ?person has an occupation (optional)
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{},en". }}
        FILTER (?person in ({}))  # QID is the Wikidata identifier for the person
        }}
        """.format(lang, ids_txt)
    else:
        return """
        SELECT ?person ?personLabel ?dateOfBirth ?dateOfDeath ?genderLabel ?countryOfCitizenshipLabel ?occupationLabel
        WHERE
        {{
        ?person wdt:P31 wd:Q5 .  # ?person is a human
        ?person wdt:P569 ?dateOfBirth .  # ?person has a date of birth
        OPTIONAL {{ ?person wdt:P570 ?dateOfDeath . }}  # ?person has a date of death (optional)
        OPTIONAL {{ ?person wdt:P21 ?gender . }}  # ?person has a gender (optional)
        OPTIONAL {{ ?person wdt:P27 ?countryOfCitizenship . }}  # ?person has a country of citizenship (optional)
        OPTIONAL {{ ?person wdt:P106 ?occupation . }}  # ?person has an occupation (optional)
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{},en". }}
        FILTER (?person in ({}))  # QID is the Wikidata identifier for the person
        }}
        """.format(lang, ids_txt)

def get_query_from_name(name, lang):
    return """
    SELECT ?person ?personLabel ?dateOfBirth ?dateOfDeath ?genderLabel ?countryOfCitizenshipLabel ?occupationLabel
    WHERE
    {{
      ?person wdt:P31 wd:Q5 .  # ?person is a human
      ?person rdfs:label "{}"@en .  # ?person has a label (name)
      ?person wdt:P569 ?dateOfBirth .  # ?person has a date of birth 
      OPTIONAL {{ ?person wdt:P570 ?dateOfDeath . }}  # ?person has a date of death (optional)
      OPTIONAL {{ ?person wdt:P21 ?gender . }}  # ?person has a gender (optional)
      OPTIONAL {{ ?person wdt:P27 ?countryOfCitizenship . }}  # ?person has a country of citizenship (optional)
      OPTIONAL {{ ?person wdt:P106 ?occupation . }}  # ?person has an occupation (optional)
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{},en". }}
    }}
    """.format(name.title(), lang)
