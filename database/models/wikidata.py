import re
import requests
import pandas as pd

from sqlalchemy.orm import Session

from .athlet import Athlet

WIKIMEDIA_ID_FORMAT = r"^Q\d+$"
WIKIDATA_URL = "https://query.wikidata.org/sparql"
WIKIDATA_REST_URL = "https://www.wikidata.org/w/api.php"
HEADERS = {'User-Agent': 'Fantamorto/0.0 (https://t.me/NewFantamortoBot; tonin.ale@gmail.com)'}
WIKIDATA_COLUMNS = {
    'person.value': "personID",
    'personLabel.value': "label",
    'dateOfBirth.value': "birth",
    'dateOfDeath.value': "death",
    'gender.value': "genderID",
    'genderLabel.value': "gender",
    'citizenship.value': "citizenshipID",
    'citizenshipLabel.value': "citizenship",
    'occupation.value': "occupationID",
    'occupationLabel.value': "occupation",
}
ID_COLUMNS = [
    "personID",
    "genderID",
    "citizenshipID",
    "occupationID"
]

PROPERTIES_ID = {
    "gender": "P21",
    "citizenship": "P27",
    "occupation": "P106"
}


def get_athlet(session: Session, input:str|list[str], alive:bool=True, only_deads:bool=False) -> list[Athlet]:
    athlets = []

    # Retrieve basic info using Sparql
    df = get_athlet_info(input, only_deads=only_deads)
    if df.empty:
        return athlets

    if alive:
        df = df[df["death"] == ''].sort_values(by=["birth"]).reset_index(drop=True)
    
    wids = df.personID.to_list()

    ordered_properties = get_athlets_ordered_properties(wids=wids)
    
    for _, athlet in df.iterrows():
        wiki_id = athlet.personID
        genders_idx = [athlet.genderID.index(x) for x in ordered_properties[wiki_id]["genders"]]
        citizenships_idx = [athlet.citizenshipID.index(x) for x in ordered_properties[wiki_id]["citizenships"]]
        occupations_idx = [athlet.occupationID.index(x) for x in ordered_properties[wiki_id]["occupations"]]
        # import pdb
        # pdb.set_trace()
        p = Athlet.get_or_create(
            session=session,
            name=athlet.label,
            dob=athlet.birth,
            dod=athlet.death if athlet.death else None,
            WID=wiki_id,
            genders=[(athlet.genderID[x], athlet.gender[x]) for x in genders_idx],
            citizenships=[(athlet.citizenshipID[x],athlet.citizenship[x]) for x in citizenships_idx],
            occupations=[(athlet.occupationID[x],athlet.occupation[x]) for x in occupations_idx],
        )
        athlets.append(p)
    return athlets


def find_dead_athlets(session: Session, ids:list[str]) -> list[Athlet]:
    # updated_athlets = {}
    # for id, pers in dict_athlets.items():
    #     updated_pers = get_athlet(id, alive=False, lang=lang, only_deads=True)
    #     if (pers.dod != updated_pers.dod or
    #        pers.genders != updated_pers.genders or
    #        pers.citizenships != updated_pers.citizenships or
    #        pers.occupations != updated_pers.occupations):
    #         updated_athlets[id] = updated_pers
    updated_athlets = get_athlet(session, ids, alive=False, only_deads=True)
    return updated_athlets
 

def get_athlet_info(input:str|list[str], only_deads:bool=False) -> pd.DataFrame:
    if type(input) is list or re.match(WIKIMEDIA_ID_FORMAT, input):
        query = get_query_sparql(input=input, is_id=True, only_deads=only_deads)
    else:
        query = get_query_sparql(input=input, is_id=False, only_deads=only_deads)
    # Set the headers and parameters for the request
    # headers = {
    #     'Content-Type': 'application/x-www-form-urlencoded',
    # }
    params = {
        'format': 'json',
        'query': query
    }

    # Send the request and get the response
    response = requests.get(WIKIDATA_URL, params=params, headers=HEADERS)
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


def get_query_df(data: dict) -> pd.DataFrame:
    df = pd.json_normalize(data["results"]["bindings"])
    if df.empty:
        return df
    discarded_columns = [c for c in df.columns if c not in WIKIDATA_COLUMNS]
    missing_columns = [c for c in WIKIDATA_COLUMNS if c not in df.columns]
    df.drop(labels=discarded_columns, axis=1, inplace=True)
    df[missing_columns] = ''
    df.fillna('', inplace=True)
    df.rename(columns=WIKIDATA_COLUMNS, inplace=True)
    # Replace wikimedia url with ID
    for col in ID_COLUMNS:
        df[col] = df[col].str.extract(r'http://www.wikidata.org/entity/(Q\d+)')
    grouped = df.groupby(["personID", "birth", "label", "death"]).agg(lambda x: list(x)).reset_index()
    with_dob = grouped[grouped["birth"] != ""].reset_index(drop=True)
    return with_dob


def is_unique_athlet(df:pd.DataFrame) -> bool:
    if len(df["person"].unique()) == 1:
        return True
    else:
        return False


def get_query_sparql(input:str|list[str], is_id:bool=False, only_deads:bool=False) -> str:
    
    query = """
        SELECT DISTINCT ?person ?personLabel ?dateOfBirth ?dateOfDeath ?gender ?genderLabel ?citizenship ?citizenshipLabel ?occupation ?occupationLabel 
        WHERE {
            {
                SERVICE wikibase:label { bd:serviceParam wikibase:language "it,en". }
                ?person wdt:P31 wd:Q5;
                wdt:P569 ?dateOfBirth."""
    if only_deads:
        query += "?person wdt:P570 ?dateOfDeath."
    else:
        query += "OPTIONAL { ?person wdt:P570 ?dateOfDeath. }"
                
    query += """
                OPTIONAL {
                    ?person p:P21 ?stG.
                    ?stG ps:P21 ?gender.
                    MINUS { ?stG wikibase:rank wikibase:DeprecatedRank. }
                }
                OPTIONAL {
                    ?person p:P27 ?stC.
                    ?stC ps:P27 ?citizenship.
                    MINUS { ?stC wikibase:rank wikibase:DeprecatedRank. }
                }
                OPTIONAL {
                    ?person p:P106 ?stO.
                    ?stO ps:P106 ?occupation.
                    MINUS { ?stO wikibase:rank wikibase:DeprecatedRank. }
                }"""

    if is_id:
        if type(input) is list:
            ids = ", ".join([f"wd:{id}" for id in input])
            query += f"FILTER (?person in ({ids}))"  # QID is the Wikidata identifier for the person
        else:
            query += f"FILTER (?person = wd:{input})"  # QID is the Wikidata identifier for the person
    else:
        query += f"""
                {{ ?person rdfs:label "{input.title()}"@it. }}
                UNION
                {{ ?person rdfs:label "{input.title()}"@en. }}
                """
    query += """        
            }
        }
    """
    return query


def get_athlets_ordered_properties(wids:list[str]) -> dict:
    ids = '|'.join(wids)
    params = {
            'action': 'wbgetentities',
            'ids': ids,
            'format': 'json',
            'languages': 'en'
        }
    response = requests.get(WIKIDATA_REST_URL, params=params, headers=HEADERS)
    if response.status_code != 200:
        # The request was not successful, so return None
        raise requests.ConnectionError(f"Wikidata problem. Response status code: {response.status_code}")

    data = response.json()
    ordered_properties = {}
    for id in wids:
        # Genders ordered
        data_property = data['entities'][id]
        genders_ids = get_ordered_property(data_property, PROPERTIES_ID["gender"])
        citizenships_ids = get_ordered_property(data_property, PROPERTIES_ID["citizenship"])
        occupations_ids = get_ordered_property(data_property, PROPERTIES_ID["occupation"])
        
        # Store in dictionary
        ordered_properties[id] = {
            "genders": genders_ids,
            "citizenships": citizenships_ids,
            "occupations": occupations_ids
        }

    return ordered_properties

def get_ordered_property(data:dict, propertyID:str) -> list[str]:
    prop_data = data['claims'].get(propertyID,[])
    prop_pref = []
    prop_norm = []
    for property in prop_data:
        valueID = property['mainsnak']['datavalue']['value']['id']
        if property["rank"] == "deprecated":
            continue
        elif property["rank"] == "preferred":
            prop_pref.append(valueID)
        else:
            prop_norm.append(valueID)

    return prop_pref + prop_norm  