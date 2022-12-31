import re
import requests
import pandas as pd
from .fantamorto import Person

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


def get_person(input, alive=True, lang="it"):
    persons = []

    df = get_person_info(input, lang)
    if df.empty:
        return persons

    if alive:
        df = df[df["death"] == ''].sort_values(by=["birth"]).reset_index(drop=True)
    
    for _, person in df.iterrows():
        p = Person(
            name=person.label,
            dob=person.birth,
            dod=person.death if person.death else None,
            WID=person.person.split("/")[-1],
            citizenships=[c for c in person.citizienship if c],
            genders=[g for g in person.gender if g],
            occupations=[o for o in person.occupation if o],
        )
        persons.append(p)
    return persons


def update_persons(dict_persons: dict, lang="it") -> dict:
    updated_persons = {}
    for id, pers in dict_persons.items():
        updated_pers = get_person(id, alive=False, lang=lang)
        if (pers.dod != updated_pers.dod or
           pers.genders != updated_pers.genders or
           pers.citizenships != updated_pers.citizenships or
           pers.occupations != updated_pers.occupations):
            updated_persons[id] = updated_pers
    return updated_persons


def get_person_info(input: str, lang: str) -> pd.DataFrame:
    if re.match(WIKIMEDIA_ID_FORMAT, input):
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

        # if not is_unique_person(df):
        #     raise ValueError("Too many results, try to directly send the Wikimedia ID")

        return df
    else:
        # The request was not successful, so return None
        raise requests.ConnectionError(f"Wikidata problem. Response status code: {response.status_code}")


def get_query_df(data):
    df = pd.json_normalize(data["results"]["bindings"])
    discarded_columns = [c for c in df.columns if c not in WIKIDATA_COLUMNS]
    missing_columns = [c for c in WIKIDATA_COLUMNS if c not in df.columns]
    df.drop(labels=discarded_columns, axis=1, inplace=True)
    df[missing_columns] = ''
    df.fillna('', inplace=True)
    df.rename(columns=WIKIDATA_COLUMNS, inplace=True)
    grouped = df.groupby(["person", "birth", "label", "death"]).agg(lambda x: sorted(list(set(x)))).reset_index()

    return grouped


def is_unique_person(df):
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
      OPTIONAL {{ ?person wdt:P569 ?dateOfBirth . }}  # ?person has a date of birth (optional)
      OPTIONAL {{ ?person wdt:P570 ?dateOfDeath . }}  # ?person has a date of death (optional)
      OPTIONAL {{ ?person wdt:P21 ?gender . }}  # ?person has a gender (optional)
      OPTIONAL {{ ?person wdt:P27 ?countryOfCitizenship . }}  # ?person has a country of citizenship (optional)
      OPTIONAL {{ ?person wdt:P106 ?occupation . }}  # ?person has an occupation (optional)
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{},en". }}
      FILTER (?person = wd:{})  # QID is the Wikidata identifier for the person
    }}
    """.format(lang, id)

def get_query_from_name(name, lang):
    return """
    SELECT ?person ?personLabel ?dateOfBirth ?dateOfDeath ?genderLabel ?countryOfCitizenshipLabel ?occupationLabel
    WHERE
    {{
      ?person wdt:P31 wd:Q5 .  # ?person is a human
      ?person rdfs:label "{}"@en .  # ?person has a label (name)
      OPTIONAL {{ ?person wdt:P569 ?dateOfBirth . }}  # ?person has a date of birth (optional)
      OPTIONAL {{ ?person wdt:P570 ?dateOfDeath . }}  # ?person has a date of death (optional)
      OPTIONAL {{ ?person wdt:P21 ?gender . }}  # ?person has a gender (optional)
      OPTIONAL {{ ?person wdt:P27 ?countryOfCitizenship . }}  # ?person has a country of citizenship (optional)
      OPTIONAL {{ ?person wdt:P106 ?occupation . }}  # ?person has an occupation (optional)
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{},en". }}
    }}
    """.format(name.title(), lang)
