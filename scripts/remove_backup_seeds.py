import os
from typing import Union
import argparse
import csv
import re
import pandas as pd
from tabulate import tabulate


def read_table(filepath: str) -> pd.DataFrame:
    """
    Reads an existing prescale table file from a local path.

    Parameters
    ----------
    filepath : str
        Local path of the input file

    Returns
    -------
    pandas.DataFrame
        Imported prescale table as a DataFrame

    """

    if not os.path.exists(filepath):
        raise RuntimeError('Error opening the file {}'.format(filepath))

    table = pd.DataFrame()

    if filepath.endswith('.csv'):
        with open(filepath, 'r') as csv_table:
            table = pd.read_csv(filepath, sep=None, header=0, engine='python')

    else:
        raise RuntimeError('Unsupported input file format')

    return table


def get_PS_col_idx(table: pd.DataFrame) -> int:
    """
    Find and return the index of the prescale column in a PS table.

    Parameters
    ----------
    table : pandas.DataFrame
        PS table from which the prescale column index should be determined

    Returns
    -------
    int
        The index of the identified prescale column.

    """

    identifiers = ['prescale','ps']
    ps_header_bool = [col.lower() in identifiers for col in table.columns.values]

    # make sure the PS column naming is unique
    if (ps_header_bool).count(True) != 1:
        raise RuntimeError('None or more than one prescale columns '
                'identified - check the table column names')

    return ps_header_bool.index(True)


def get_name_col_idx(table: pd.DataFrame) -> int:
    """
    Find and return the index of the seed name colum in a prescale table.

    The seed name column is determined to be the columns with the most
    occurrences of the string pattern "L1_*".

    Parameters
    ----------
    table : pandas.DataFrame
        PS table from which the prescale column index should be determined

    Returns
    -------
    int
        The index of the identified seed name column.

    """

    cnt_L1occurences = [0 for col in table.columns.values]
    for __,row in table.iterrows():
        for idx,col in enumerate(table.columns.values):
            if type(row[col]) == str and  row[col].startswith('L1_'):
                cnt_L1occurences[idx] += 1

    if all([col == 0 for col in cnt_L1occurences]):
        raise RuntimeError('Error identifying the seed name column - make sure '
                'that the seed names start with \'L1_\'')

    return cnt_L1occurences.index(max(cnt_L1occurences))


def get_all_seed_basenames(seeds: list) -> list:
    # TODO add docstring

    basenames = []

    for seed in seeds:
        if type(seed) != str:
            print('Invalid type: {} ({})'.format(seed,type(seed)))
            continue
        if not seed.startswith('L1_'):
            print('Invalid seed: {}'.format(seed))
            continue

        temp_basename = seed.replace('L1_','')
        temp_basename = temp_basename.split('_')[0]  # only keep until first "_"
        digits = re.search('\d', temp_basename)
        if digits: temp_basename = temp_basename[0:digits.start()]

        if temp_basename not in basenames: basenames.append('L1_'+temp_basename)

    return basenames


def get_seed_basename(seed: str) -> str:
    # TODO add docstring

    if not seed.startswith('L1_'):
        return None

    basename = seed.replace('L1_','')  # temporarily remove this prefix
    basename = basename.split('_')[0]  # strip the part after the first "_"
    digits = re.search('\d', basename)
    if digits: basename = basename[0:digits.start()]  # keep until first digit

    return 'L1_'+basename


def convert_to_float(val: str) -> Union[float,None]:
    """
    Takes a string and tries to convert it to a float.

    Parameters
    ----------
    val : str
        String holding the float number, examples of allowed format are '1.2'
        and '1p2'.

    Returns
    -------
    float, None
        The converted number as a float, None if the conversion was unsuccessful

    """

    return_val = None

    if val is None: return return_val

    val = val.replace('_','')  # just to be sure
    if 'p' in val: val = val.replace('p','.')
    try:
        return_val = float(val)
    except ValueError:
        pass

    return return_val



def separate_signal_and_backup_seeds(table: pd.DataFrame, verbose=True) -> (pd.DataFrame,
        pd.DataFrame):
    # TODO add docstring

    signal_seeds = pd.DataFrame(columns=table.columns)
    backup_seeds = pd.DataFrame(columns=table.columns)

    backup_seeds_info = []

    name_col_idx = get_name_col_idx(table)
    PS_col_idx = get_PS_col_idx(table)

    for idx,row in table.iterrows():
        seed = row[name_col_idx]
        prescale = row[PS_col_idx]

        is_backup_seed, identified_signal_seeds, criteria = has_signal_seed(seed, prescale,
                table.iloc[:,name_col_idx].tolist(), table.iloc[:,PS_col_idx].tolist())

        if is_backup_seed:
            backup_seeds = backup_seeds.append(table.iloc[idx,:])
            backup_seeds_info.append([seed, ', '.join(identified_signal_seeds),
                ', '.join(criteria)])

        else:
            signal_seeds = signal_seeds.append(table.iloc[idx,:])

    if verbose:
        print(tabulate(backup_seeds_info, headers=['Identified backup seed',
            'corresponding signal seeds',
            'used criteria (in signal seed order)']))

    return signal_seeds, backup_seeds


def has_signal_seed(seed: str, prescale: int, all_seeds: list,
        all_prescales: list) -> (bool, list, list):
    # TODO add docstring

    # collection of functions that define backup-seed criteria
    criterion_functions = [
        criterion_prescale,
        criterion_pT,
        criterion_er,
        criterion_dRmax,
        criterion_dRmin,
        criterion_MassXtoY,
        criterion_quality,
        criterion_isolation,
    ]

    is_backup_seed = False
    identified_signal_seeds = []
    criteria = []

    for otherseed,otherprescale in zip(all_seeds, all_prescales):
        for criterion in criterion_functions:
            if not all([type(s) == str for s in (seed,otherseed)]): continue
            is_backup_candidate, identified_signal_seed, identified_criterion = criterion(
                    seed, prescale, otherseed, otherprescale)

            if is_backup_candidate:
                is_backup_seed = True
                identified_signal_seeds.append(identified_signal_seed)
                criteria.append(identified_criterion)

    return is_backup_seed, identified_signal_seeds, criteria


def criterion_pT(seed: str, prescale: int, otherseed: str, otherprescale: int) -> (bool, str, str):
    """
    Checks whether 'seed' has a tigher pT cut than 'otherseed'.

    Supported formats (all formats allow for an optional single underscore
    before the first threshold value, all further threshold values must be
    separated by '_'):
    - single object seeds of the form L1_[NAME][THRESHOLD]*
    - double object seeds of the form L1_*double*[THRESHOLD] or
      L1_*double*[THRESHOLD1]_[THRESHOLD2]
    - triple object seeds of the form L1_*triple*[THRESHOLD]* or
      L1_*triple*[THRESHOLD1]_[THRESHOLD2]_[THRESHOLD3]
    - quadruple object seeds of the form L1_*quad*[THRESHOLD]* or
      L1_*quad*[THRESHOLD1]_[THRESHOLD2]_[THRESHOLD3]_[THRESHOLD4]

    In case of multi-object seeds, all given thresholds of 'otherseed' must
    individually be greater than or equal to the respective thresholds of
    'seed' in order for the latter to be considered as a backup seed candidate
    (i.e., 'seed' is not immediately discarded).

    If 'seed' and 'otherseed' have any differences apart from their pT cuts,
    this function will not process them.

    Note: This function does not yet work for seeds with an eta criterion
    directly attached to the pT threshold (e.g., L1_SingleMu6er1p5).

    Parameters
    ---------
    seed : str
        Name of the seed which is checked for its 'backup seed' properties
    precale : int
        Prescale value for 'seed'
    otherseed : str
        Name of the algorithm which 'seed' is checked against
    otherprescale : int
        Prescale value for 'otherseed'

    Returns
    -------
    (bool, str, str)
        True if 'seed' is a backup seed to 'otherseed' or False otherwise,
        the name of the other seed if 'otherseed' is a signal seed to 'seed' or
        None otherwise, name of the criterion (None if 'seed' is not a backup
        seed)

    """

    is_backup_candidate = False

    seed_basename = get_seed_basename(seed)
    otherseed_basename = get_seed_basename(otherseed)

    # skip if different seeds altogether
    if seed_basename != otherseed_basename:
        return False, None, None
    elif seed_basename is None or otherseed_basename is None:
        return False, None, None

    # distinguish between single, double, triple and quadruple seed objects

    # process single-object case first
    if not any([t in seed_basename.lower() for t in ('double','triple','quad')]):
        pattern = r'{}(_*?)(\d+p\d+|\d+)($|\_[a-zA-Z]+)'.format(seed_basename)

        seed_pt_str = re.search(pattern, seed)
        if seed_pt_str:
            seed_stripped = seed.replace(
                    seed_basename + seed_pt_str.group(1) + seed_pt_str.group(2),
                    seed_basename)
            seed_pt_threshold = convert_to_float(seed_pt_str.group(2))
            seed_pt_str = seed_pt_str.group(0)
        else:
            seed_stripped = seed
            seed_pt_threshold = None

        otherseed_pt_str = re.search(pattern, otherseed)
        if otherseed_pt_str:
            otherseed_stripped = otherseed.replace(
                    otherseed_basename + otherseed_pt_str.group(1) + \
                            otherseed_pt_str.group(2), otherseed_basename)
            otherseed_pt_threshold = convert_to_float(otherseed_pt_str.group(2))
            otherseed_pt_str = otherseed_pt_str.group(0)
        else:
            otherseed_stripped = otherseed
            otherseed_pt_threshold = None

        # skip if seeds are different apart from their pT criterion
        if seed_stripped != otherseed_stripped:
            return False, None, None

        if seed_pt_threshold is not None and otherseed_pt_threshold is not None \
                and seed_pt_threshold > otherseed_pt_threshold:
            is_backup_candidate = True

    # process double-object seeds
    elif 'double' in seed_basename.lower():
        pattern = r'{}(_*?)(\d+p\d+|\d+)($|(\_(\d+p\d+|\d+)|\_[a-zA-Z]+))'.format(seed_basename)

        seed_pt_str = re.search(pattern, seed)
        if seed_pt_str:
            seed_stripped = seed.replace(
                    seed_basename + seed_pt_str.group(1) + seed_pt_str.group(2),
                    seed_basename)
            seed_pt_threshold_1 = convert_to_float(seed_pt_str.group(2))
            seed_pt_threshold_2 = convert_to_float(seed_pt_str.group(3))
            seed_pt_str = seed_pt_str.group(0)
        else:
            seed_stripped = seed
            seed_pt_threshold_1 = None
            seed_pt_threshold_2 = None

        otherseed_pt_str = re.search(pattern, otherseed)
        if otherseed_pt_str:
            otherseed_stripped = otherseed.replace(
                    otherseed_basename + otherseed_pt_str.group(1) + \
                            otherseed_pt_str.group(2), otherseed_basename)
            otherseed_pt_threshold_1 = convert_to_float(otherseed_pt_str.group(2))
            otherseed_pt_threshold_2 = convert_to_float(otherseed_pt_str.group(3))
            otherseed_pt_str = otherseed_pt_str.group(0)
        else:
            otherseed_stripped = otherseed
            otherseed_pt_threshold_1 = None
            otherseed_pt_threshold_2 = None

        # skip if seeds are different apart from their pT criteria
        if seed_stripped != otherseed_stripped:
            return False, None, None

        seed_types = [type(t) for t in (seed_pt_threshold_1,
            seed_pt_threshold_2)]
        otherseed_types = [type(t) for t in (otherseed_pt_threshold_1,
            otherseed_pt_threshold_2)]

        allowed_types = ([float, None], [float, float])

        if any([types not in allowed_types for types in \
                (seed_types, otherseed_types)]):
            return False, None, None

        if all([types == [float, None] for types in \
                (seed_types, otherseed_types)]):
            if seed_pt_threshold_1 > otherseed_pt_threshold_1:
                is_backup_candidate = True

        if all([types == [float, float] for types in \
                (seed_types, otherseed_types)]):
            if seed_pt_threshold_1 >= otherseed_pt_threshold_1 and \
                    seed_pt_threshold_2 >= otherseed_pt_threshold_2 and \
                    (seed_pt_threshold_1 > otherseed_pt_threshold_1 or \
                    seed_pt_threshold_2 > otherseed_pt_threshold_2):
                is_backup_candidate = True

    # process triple-object seeds
    elif 'triple' in seed_basename.lower():
        pattern = r'{}(_*?)(\d+p\d+|\d+)($|(\_(\d+p\d+|\d+)\_(\d+p\d+|\d+)|\_[a-zA-Z]+))'.format(seed_basename)

        seed_pt_str = re.search(pattern, seed)
        if seed_pt_str:
            if convert_to_float(seed_pt_str.group(3)) is not None:
                replace_str = seed_basename + seed_pt_str.group(1) + \
                        seed_pt_str.group(2) + seed_pt_str.group(3)
            else:
                replace_str = seed_basename + seed_pt_str.group(1) + \
                        seed_pt_str.group(2)

            seed_stripped = seed.replace(replace_str, seed_basename)
            seed_pt_threshold_1 = convert_to_float(seed_pt_str.group(2))
            if seed_pt_str.group(5):
                seed_pt_threshold_2 = convert_to_float(seed_pt_str.group(5))
            else:
                seed_pt_threshold_2 = None

            if seed_pt_str.group(6):
                seed_pt_threshold_3 = convert_to_float(seed_pt_str.group(6))
            else:
                seed_pt_threshold_3 = None

            seed_pt_str = seed_pt_str.group(0)
        else:
            seed_stripped = seed
            seed_pt_threshold_1 = None
            seed_pt_threshold_2 = None
            seed_pt_threshold_3 = None

        otherseed_pt_str = re.search(pattern, otherseed)
        if otherseed_pt_str:
            if convert_to_float(otherseed_pt_str.group(3)) is not None:
                replace_str = otherseed_basename + otherseed_pt_str.group(1) + \
                        otherseed_pt_str.group(2) + otherseed_pt_str.group(3)
            else:
                replace_str = otherseed_basename + otherseed_pt_str.group(1) + \
                        otherseed_pt_str.group(2)

            otherseed_stripped = otherseed.replace(replace_str,
                    otherseed_basename)
            otherseed_pt_threshold_1 = convert_to_float(otherseed_pt_str.group(2))
            if otherseed_pt_str.group(5):
                otherseed_pt_threshold_2 = convert_to_float(otherseed_pt_str.group(5))
            else:
                otherseed_pt_threshold_2 = None

            if otherseed_pt_str.group(6):
                otherseed_pt_threshold_3 = convert_to_float(otherseed_pt_str.group(6))
            else:
                otherseed_pt_threshold_3 = None

            otherseed_pt_str = otherseed_pt_str.group(0)
        else:
            otherseed_stripped = otherseed
            otherseed_pt_threshold_1 = None
            otherseed_pt_threshold_2 = None
            otherseed_pt_threshold_3 = None

        # skip if seeds are different apart from their pT criteria
        if seed_stripped != otherseed_stripped:
            return False, None, None

        seed_types = [type(t) for t in (seed_pt_threshold_1,
            seed_pt_threshold_2, seed_pt_threshold_3)]
        otherseed_types = [type(t) for t in (otherseed_pt_threshold_1,
            otherseed_pt_threshold_2, otherseed_pt_threshold_3)]

        allowed_types = ([float, type(None), type(None)], [float, float, float])

        if any([types not in allowed_types for types in \
                (seed_types, otherseed_types)]):
            return False, None, None

        if all([types == [float, type(None), type(None)] for types in \
                (seed_types, otherseed_types)]):
            if seed_pt_threshold_1 > otherseed_pt_threshold_1:
                is_backup_candidate = True

        if all([types == [float, float, float] for types in \
                (seed_types, otherseed_types)]):
            if seed_pt_threshold_1 >= otherseed_pt_threshold_1 and \
                    seed_pt_threshold_2 >= otherseed_pt_threshold_2 and \
                    seed_pt_threshold_3 >= otherseed_pt_threshold_3 and \
                    (seed_pt_threshold_1 > otherseed_pt_threshold_1 or \
                    seed_pt_threshold_2 > otherseed_pt_threshold_2 or \
                    seed_pt_threshold_3 > otherseed_pt_threshold_3):
                is_backup_candidate = True

    # process quadruple-object seeds
    elif 'quad' in seed_basename.lower():
        pattern = r'{}(_*?)(\d+p\d+|\d+)($|(\_(\d+p\d+|\d+)\_(\d+p\d+|\d+)\_(\d+p\d+|\d+)|\_[a-zA-Z]+))'.format(seed_basename)

        seed_pt_str = re.search(pattern, seed)
        if seed_pt_str:
            if convert_to_float(seed_pt_str.group(3)) is not None:
                replace_str = seed_basename + seed_pt_str.group(1) + \
                        seed_pt_str.group(2) + seed_pt_str.group(3)
            else:
                replace_str = seed_basename + seed_pt_str.group(1) + \
                        seed_pt_str.group(2)

            seed_stripped = seed.replace(replace_str, seed_basename)

            seed_pt_threshold_1 = convert_to_float(seed_pt_str.group(2))
            if seed_pt_str.group(5):
                seed_pt_threshold_2 = convert_to_float(seed_pt_str.group(5))
            else:
                seed_pt_threshold_2 = None

            if seed_pt_str.group(6):
                seed_pt_threshold_3 = convert_to_float(seed_pt_str.group(6))
            else:
                seed_pt_threshold_3 = None

            if seed_pt_str.group(7):
                seed_pt_threshold_4 = convert_to_float(seed_pt_str.group(7))
            else:
                seed_pt_threshold_4 = None

            seed_pt_str = seed_pt_str.group(0)
        else:
            seed_stripped = seed
            seed_pt_threshold_1 = None
            seed_pt_threshold_2 = None
            seed_pt_threshold_3 = None
            seed_pt_threshold_4 = None

        otherseed_pt_str = re.search(pattern, otherseed)
        if otherseed_pt_str:
            if convert_to_float(otherseed_pt_str.group(3)) is not None:
                replace_str = otherseed_basename + otherseed_pt_str.group(1) + \
                        otherseed_pt_str.group(2) + otherseed_pt_str.group(3)
            else:
                replace_str = otherseed_basename + otherseed_pt_str.group(1) + \
                        otherseed_pt_str.group(2)

            otherseed_stripped = otherseed.replace(replace_str,
                    otherseed_basename)

            otherseed_pt_threshold_1 = convert_to_float(otherseed_pt_str.group(2))
            if otherseed_pt_str.group(5):
                otherseed_pt_threshold_2 = convert_to_float(otherseed_pt_str.group(5))
            else:
                otherseed_pt_threshold_2 = None

            if otherseed_pt_str.group(6):
                otherseed_pt_threshold_3 = convert_to_float(otherseed_pt_str.group(6))
            else:
                otherseed_pt_threshold_3 = None

            if otherseed_pt_str.group(7):
                otherseed_pt_threshold_4 = convert_to_float(otherseed_pt_str.group(7))
            else:
                otherseed_pt_threshold_4 = None

            otherseed_pt_str = otherseed_pt_str.group(0)
        else:
            otherseed_stripped = otherseed
            otherseed_pt_threshold_1 = None
            otherseed_pt_threshold_2 = None
            otherseed_pt_threshold_3 = None
            otherseed_pt_threshold_4 = None

        # skip if seeds are different apart from their pT criteria
        if seed_stripped != otherseed_stripped:
            return False, None, None

        seed_types = [type(t) for t in (seed_pt_threshold_1, seed_pt_threshold_2,
            seed_pt_threshold_3, seed_pt_threshold_4)]
        otherseed_types = [type(t) for t in (otherseed_pt_threshold_1,
            otherseed_pt_threshold_2, otherseed_pt_threshold_3,
            otherseed_pt_threshold_4)]

        allowed_types = ([float, type(None), type(None), type(None)],
                [float, float, float, float])

        if any([types not in allowed_types for types in (seed_types, otherseed_types)]):
            return False, None, None

        if all([types == [float, type(None), type(None), type(None)] for types \
                in (seed_types, otherseed_types)]):
            if seed_pt_threshold_1 > otherseed_pt_threshold_1:
                is_backup_candidate = True

        if all([types == [float, float, float, float] for types in \
                (seed_types, otherseed_types)]):
            if seed_pt_threshold_1 >= otherseed_pt_threshold_1 and \
                    seed_pt_threshold_2 >= otherseed_pt_threshold_2 and \
                    seed_pt_threshold_3 >= otherseed_pt_threshold_3 and \
                    seed_pt_threshold_4 >= otherseed_pt_threshold_4 and \
                    (seed_pt_threshold_1 > otherseed_pt_threshold_1 or \
                    seed_pt_threshold_2 > otherseed_pt_threshold_2 or \
                    seed_pt_threshold_3 > otherseed_pt_threshold_3 or \
                    seed_pt_threshold_4 > otherseed_pt_threshold_4):
                is_backup_candidate = True

    return is_backup_candidate, (otherseed if is_backup_candidate else None), \
            ('pT' if is_backup_candidate else None)


def criterion_er(seed: str, prescale: int, otherseed: str, otherprescale: int) -> (bool, str, str):
    """
    Checks whether 'seed' has a tigher eta restriction cut than 'otherseed'.

    Eta restriction: |eta| < threshold. If not explicitly specified, no eta
    restrictions are applied.

    This function does not process any seeds which involve more than one eta
    restriction (e.g., cross-triggers). Further, if 'seed' and 'otherseed' have
    any differences apart from their eta restrictions, this function will pass
    on them as well.

    Parameters
    ---------
    seed : str
        Name of the seed which is checked for its 'backup seed' properties
    precale : int
        Prescale value for 'seed'
    otherseed : str
        Name of the algorithm which 'seed' is checked against
    otherprescale : int
        Prescale value for 'otherseed'

    Returns
    -------
    (bool, str)
        True if 'seed' is a backup seed to 'otherseed' or False otherwise,
        the name of the other seed if 'otherseed' is a signal seed to 'seed' or
        None otherwise, name of the criterion function (None if 'seed' is not a
        backup seed)

    """

    is_backup_candidate = False

    seed_basename = get_seed_basename(seed)
    otherseed_basename = get_seed_basename(otherseed)

    # skip if different seeds altogether
    if seed_basename != otherseed_basename:
        return False, None, None

    # do not process further if there are multiple eta restrictions in a seed
    pattern = r'er(\d+)p(\d+)|er(\d+)'
    if any([len(re.findall(pattern, s)) > 1 for s in (seed, otherseed)]):
        return False, None, None

    # do not process further if neither seed has an eta restriction
    if all([len(re.findall(pattern, s)) == 0 for s in (seed, otherseed)]):
        return False, None, None

    # extract the eta restriction substring for 'seed'
    seed_er_str = re.search(pattern, seed)
    if seed_er_str:
        seed_er_str = seed_er_str.group(0)
        seed_stripped = seed.replace(seed_er_str,'')
    else:
        seed_stripped = seed

    # extract the eta restriction substring for 'otherseed'
    otherseed_er_str = re.search(pattern, otherseed)
    if otherseed_er_str:
        otherseed_er_str = otherseed_er_str.group(0)
        otherseed_stripped = otherseed.replace(otherseed_er_str,'')
    else:
        otherseed_stripped = otherseed

    # do not process further if the seeds are different (apart from their ER)
    if seed_stripped != otherseed_stripped:
        return False, None, None

    if seed_er_str is not None:
        seed_er_val = convert_to_float(seed_er_str.replace('er',''))
    else:
        seed_er_val = None

    if otherseed_er_str is not None:
        otherseed_er_val = convert_to_float(otherseed_er_str.replace('er',''))
    else:
        otherseed_er_val = None

    if seed_er_val is not None and otherseed_er_val is not None and \
            seed_er_val < otherseed_er_val:
        is_backup_candidate = True

    if seed_er_val is not None and otherseed_er_val is None and \
            seed_er_val > 0.0:
        is_backup_candidate = True

    return is_backup_candidate, (otherseed if is_backup_candidate else None), \
            ('eta restriction' if is_backup_candidate else None)


def criterion_dRmax(seed: str, prescale: int, otherseed: str, otherprescale: int) -> (bool, str, str):
    """
    Checks whether 'seed' has a tigher dRmax restriction cut than 'otherseed'.

    If not explicitly specified, no dRmax restriction is applied.

    This function does not process any seeds which involve more than one dRmax
    restriction (e.g., cross-triggers). Further, if 'seed' and 'otherseed' have
    any differences apart from their dRmax restrictions, this function will pass
    on them as well.

    Parameters
    ---------
    seed : str
        Name of the seed which is checked for its 'backup seed' properties
    precale : int
        Prescale value for 'seed'
    otherseed : str
        Name of the algorithm which 'seed' is checked against
    otherprescale : int
        Prescale value for 'otherseed'

    Returns
    -------
    (bool, str)
        True if 'seed' is a backup seed to 'otherseed' or False otherwise,
        the name of the other seed if 'otherseed' is a signal seed to 'seed' or
        None otherwise, name of the criterion (None if 'seed' is not a backup
        seed)

    """

    is_backup_candidate = False

    seed_basename = get_seed_basename(seed)
    otherseed_basename = get_seed_basename(otherseed)

    # skip if different seeds altogether
    if seed_basename != otherseed_basename:
        return False, None, None

    # do not process further if there are multiple dRmax restrictions
    pattern = r'dR_Max(\d+)p(\d+)|dR_Max(\d+)'
    if any([len(re.findall(pattern, s)) > 1 for s in (seed, otherseed)]):
        return False, None, None

    # do not process further if neither seed has a dRmax restriction
    if all([len(re.findall(pattern, s)) == 0 for s in (seed, otherseed)]):
        return False, None, None

    # extract the dRmax restriction substring for 'seed'
    seed_dRmax_str = re.search(pattern, seed)
    if seed_dRmax_str:
        seed_dRmax_str = seed_dRmax_str.group(0)
        seed_stripped = seed.replace(seed_dRmax_str,'')
    else:
        seed_stripped = seed

    # extract the dRmax restriction substring for 'otherseed'
    otherseed_dRmax_str = re.search(pattern, otherseed)
    if otherseed_dRmax_str:
        otherseed_dRmax_str = otherseed_dRmax_str.group(0)
        otherseed_stripped = otherseed.replace(otherseed_dRmax_str,'')
    else:
        otherseed_stripped = otherseed

    # do not process further if the seeds are different (apart from their dRmax)
    if seed_stripped != otherseed_stripped:
        return False, None, None

    if seed_dRmax_str is not None:
        seed_dRmax_val = convert_to_float(seed_dRmax_str.replace('dR_Max',''))
    else:
        seed_dRmax_val = None

    if otherseed_dRmax_str is not None:
        otherseed_dRmax_val = convert_to_float(otherseed_dRmax_str.replace('dR_Max',''))
    else:
        otherseed_dRmax_val = None

    if seed_dRmax_val is not None and otherseed_dRmax_val is not None and \
            seed_dRmax_val < otherseed_dRmax_val:
        is_backup_candidate = True

    if seed_dRmax_val is not None and otherseed_dRmax_val is None and \
            seed_dRmax_val > 0.0:
        is_backup_candidate = True

    return is_backup_candidate, (otherseed if is_backup_candidate else None), \
            ('dR_Max' if is_backup_candidate else None)


def criterion_dRmin(seed: str, prescale: int, otherseed: str, otherprescale: int) -> (bool, str, str):
    """
    Checks whether 'seed' has a tigher dRmin restriction cut than 'otherseed'.

    If not explicitly specified, no dRmin restriction is applied.

    This function does not process any seeds which involve more than one dRmin
    restriction (e.g., cross-triggers). Further, if 'seed' and 'otherseed' have
    any differences apart from their dRmin restrictions, this function will pass
    on them as well.

    Parameters
    ---------
    seed : str
        Name of the seed which is checked for its 'backup seed' properties
    precale : int
        Prescale value for 'seed'
    otherseed : str
        Name of the algorithm which 'seed' is checked against
    otherprescale : int
        Prescale value for 'otherseed'

    Returns
    -------
    (bool, str)
        True if 'seed' is a backup seed to 'otherseed' or False otherwise,
        the name of the other seed if 'otherseed' is a signal seed to 'seed' or
        None otherwise, the name of the criterion (None if 'seed' is not a
        backup seed)

    """

    is_backup_candidate = False

    seed_basename = get_seed_basename(seed)
    otherseed_basename = get_seed_basename(otherseed)

    # skip if different seeds altogether
    if seed_basename != otherseed_basename:
        return False, None, None

    # do not process further if there are multiple dRmin restrictions
    pattern = r'dR_Min(\d+)p(\d+)|dR_Min(\d+)'
    if any([len(re.findall(pattern, s)) > 1 for s in (seed, otherseed)]):
        return False, None, None

    # do not process further if neither seed has a dRmin restriction
    if all([len(re.findall(pattern, s)) == 0 for s in (seed, otherseed)]):
        return False, None, None

    # extract the dRmin restriction substring for 'seed'
    seed_dRmin_str = re.search(pattern, seed)
    if seed_dRmin_str:
        seed_dRmin_str = seed_dRmin_str.group(0)
        seed_stripped = seed.replace(seed_dRmin_str,'')
    else:
        seed_stripped = seed

    # extract the dRmin restriction substring for 'otherseed'
    otherseed_dRmin_str = re.search(pattern, otherseed)
    if otherseed_dRmin_str:
        otherseed_dRmin_str = otherseed_dRmin_str.group(0)
        otherseed_stripped = otherseed.replace(otherseed_dRmin_str,'')
    else:
        otherseed_stripped = otherseed

    # do not process further if the seeds are different (apart from their dRmin)
    if seed_stripped != otherseed_stripped:
        return False, None, None

    if seed_dRmin_str is not None:
        seed_dRmin_val = convert_to_float(seed_dRmin_str.replace('dR_Min',''))
    else:
        seed_dRmin_val = None

    if otherseed_dRmin_str is not None:
        otherseed_dRmin_val = convert_to_float(otherseed_dRmin_str.replace('dR_Min',''))
    else:
        otherseed_dRmin_val = None

    if seed_dRmin_val is not None and otherseed_dRmin_val is not None and \
            seed_dRmin_val > otherseed_dRmin_val:
        is_backup_candidate = True

    if seed_dRmin_val is not None and otherseed_dRmin_val is None and \
            seed_dRmin_val > 0.0:
        is_backup_candidate = True

    return is_backup_candidate, (otherseed if is_backup_candidate else None), \
            ('dR_Min' if is_backup_candidate else None)


def criterion_MassXtoY(seed: str, prescale: int, otherseed: str, otherprescale: int) -> (bool, str, str):
    """
    Checks whether 'seed' has a tigher mass cut than 'otherseed'.

    If not explicitly specified, no mass cuts are applied.

    This function does not process any seeds which involve more than one mass
    cut (e.g., cross-triggers). Further, if 'seed' and 'otherseed' have
    any differences apart from their mass restrictions, this function will pass
    on them as well.

    Parameters
    ---------
    seed : str
        Name of the seed which is checked for its 'backup seed' properties
    precale : int
        Prescale value for 'seed'
    otherseed : str
        Name of the algorithm which 'seed' is checked against
    otherprescale : int
        Prescale value for 'otherseed'

    Returns
    -------
    (bool, str)
        True if 'seed' is a backup seed to 'otherseed' or False otherwise,
        the name of the other seed if 'otherseed' is a signal seed to 'seed' or
        None otherwise, name of the criterion (None if 'seed' is not a backup
        seed)

    """

    is_backup_candidate = False

    seed_basename = get_seed_basename(seed)
    otherseed_basename = get_seed_basename(otherseed)

    # skip if different seeds altogether
    if seed_basename != otherseed_basename:
        return False, None, None

    # do not process further if there are multiple mass restrictions in a seed
    pattern = r'Mass(_*?)(\d+p\d+|\d+)to(\d+p\d+|\d+)'
    if any([len(re.findall(pattern, s)) > 1 for s in (seed, otherseed)]):
        return False, None, None

    # do not process further if neither seed has an mass restriction
    if all([len(re.findall(pattern, s)) == 0 for s in (seed, otherseed)]):
        return False, None, None

    # extract the mass restriction substring for 'seed'
    seed_mass_str = re.search(pattern, seed)
    if seed_mass_str:
        seed_mass_str = seed_mass_str.group(0)
        seed_stripped = seed.replace(seed_mass_str,'')
        if seed_stripped.endswith('_'): seed_stripped = seed_stripped[:-1]
    else:
        seed_stripped = seed

    # extract the mass restriction substring for 'otherseed'
    otherseed_mass_str = re.search(pattern, otherseed)
    if otherseed_mass_str:
        otherseed_mass_str = otherseed_mass_str.group(0)
        otherseed_stripped = otherseed.replace(otherseed_mass_str,'')
        if otherseed_stripped.endswith('_'): otherseed_stripped = otherseed_stripped[:-1]
    else:
        otherseed_stripped = otherseed

    # do not process further if the seeds are different (apart from their mass cuts)
    if seed_stripped != otherseed_stripped:
        return False, None, None

    if seed_mass_str is not None:
        search_res = re.search('\d', seed_mass_str)
        seed_mass_str = seed_mass_str[search_res.start():]
        seed_mass_str = seed_mass_str.split('to')
        seed_mass_range = [convert_to_float(val) for val in seed_mass_str]
    else:
        seed_mass_range = None

    if otherseed_mass_str is not None:
        search_res = re.search('\d', otherseed_mass_str)
        otherseed_mass_str = otherseed_mass_str[search_res.start():]
        otherseed_mass_str = otherseed_mass_str.split('to')
        otherseed_mass_range = [convert_to_float(val) for val in otherseed_mass_str]
    else:
        otherseed_mass_range = None

    if seed_mass_range is not None and otherseed_mass_range is not None and \
            seed_mass_range[1]-seed_mass_range[0] < otherseed_mass_range[1]-otherseed_mass_range[0]:
        is_backup_candidate = True

    if seed_mass_range is not None and otherseed_mass_range is None:
        is_backup_candidate = True

    return is_backup_candidate, (otherseed if is_backup_candidate else None), \
            ('MassXtoY' if is_backup_candidate else None)


def criterion_quality(seed: str, prescale: int, otherseed: str, otherprescale: int) -> (bool, str, str):
    """
    Checks whether 'seed' has a tighter quality criterion than 'otherseed'.

    This will only check SingleMu, DoubleMu, TripleMu and QuadMu seeds.

    Known muon quality criteria are (ordered from 'tighter' to 'looser' cuts):
    - SQ: 'single' quality
    - DQ: 'double' quality
    - OQ: 'open' quality

    Default qualities (if not explicitly given in the seed name):
    - SQ for single muon seeds
    - DQ for multi-muon seeds

    Parameters
    ---------
    seed : str
        Name of the seed which is checked for its 'backup seed' properties
    precale : int
        Prescale value for 'seed'
    otherseed : str
        Name of the algorithm which 'seed' is checked against
    otherprescale : int
        Prescale value for 'otherseed'

    Returns
    -------
    (bool, str)
        True if 'seed' is a backup seed to 'otherseed' or False otherwise,
        the name of the other seed if 'otherseed' is a signal seed to 'seed' or
        None otherwise, the name of the criterion (None if 'seed' is not a
        backup seed)

    """

    is_backup_candidate = False

    qualities = ('_SQ','_DQ','_OQ')

    seed_basename = get_seed_basename(seed)

    if seed_basename is None:
        return False, None, None

    if not any([muontype in seed_basename.lower() for muontype in ('singlemu',
            'doublemu', 'triplemu', 'quadmu')]):
        return False, None, None

    if not otherseed.startswith(seed_basename):
        return False, None, None

    do_further_checks = False

    if 'singlemu' in seed_basename.lower():
        # if single muon seed has default quality (i.e., 'SQ'; not explicitly
        # given in the seed name) and the other seed has a looser quality
        # criterion (i.e., 'DQ' or 'OQ')
        if all([quality not in seed for quality in qualities]) or '_SQ' in seed:
            is_SQ_seed = True
        else:
            is_SQ_seed = False

        if is_SQ_seed and any([quality in otherseed for quality in ('_DQ','_OQ')]):
            do_further_checks = True

        if '_DQ' in seed and '_OQ' in otherseed:
            do_further_checks = True

    # the default quality is 'DQ' for all of these seed types, so they can be
    # treated equally here
    if any([muontype in seed_basename.lower() for muontype in ('doublemu',
            'triplemu', 'quadmu')]):
        # if double muon seed has default quality (i.e., 'DQ'; not explicitly
        # given in the seed name) and the other seed has a looser quality
        # criterion (i.e., 'OQ')
        if all([quality not in seed for quality in qualities]) or '_DQ' in seed:
            is_DQ_seed = True
        else:
            is_DQ_seed = False

        if all([quality not in otherseed for quality in qualities]) or \
                '_DQ' in otherseed:
            is_DQ_otherseed = True
        else:
            is_DQ_otherseed = False

        if '_SQ' in seed and (is_DQ_otherseed or '_OQ' in otherseed):
            do_further_checks = True

        if is_DQ_seed and '_OQ' in otherseed:
            do_further_checks = True

    if do_further_checks:
        # require exact matches for the rest of the seed names
        seed_stripped = seed
        otherseed_stripped = otherseed
        for substr in ((seed_basename,) + qualities):
            seed_stripped = seed_stripped.replace(substr,'')
            otherseed_stripped = otherseed_stripped.replace(substr,'')

        if seed_stripped == otherseed_stripped:
            is_backup_candidate = True


    identified_signal_seed = otherseed if is_backup_candidate else None

    return is_backup_candidate, identified_signal_seed, \
            ('muon quality' if is_backup_candidate else None)


def criterion_prescale(seed: str, prescale: int, otherseed: str, otherprescale: int) -> (bool, str, str):
    """
    Checks whether 'seed' has a higher prescale value than 'otherseed'.

    Only checks for different prescale values. If the seed names are different,
    this function will not process them.

    Parameters
    ----------
    seed : str
        Name of the seed which is checked for its 'backup seed' properties
    precale : int
        Prescale value for 'seed'
    otherseed : str
        Name of the algorithm which 'seed' is checked against
    otherprescale : int
        Prescale value for 'otherseed'

    Returns
    -------
    (bool, str)
        True if 'seed' is a backup seed to 'otherseed' or False otherwise,
        the name of the other seed if 'otherseed' is a signal seed to 'seed' or
        None otherwise, the name of the criterion (None if 'seed' is not a
        backup seed)

    """

    is_backup_candidate = False
    identified_signal_seed = None
    if seed == otherseed and prescale > otherprescale:
        is_backup_candidate = True
        identified_signal_seed = otherseed

    return is_backup_candidate, identified_signal_seed, \
            ('prescale' if is_backup_candidate else None)


def criterion_isolation(seed: str, prescale: int, otherseed: str, otherprescale: int) -> (bool, str, str):
    """
    Checks whether 'seed' has a tigher isolation cut than 'otherseed'.

    Isolation criteria, ordered from tightest to loosest: 'Iso' -> 'LooseIso' ->
    no isolation criterion given.

    If not explicitly specified, no isolation cuts are applied.

    This function does not process any seeds which involve more than one
    isolation cut (e.g., cross-triggers). Further, if 'seed' and 'otherseed'
    have any differences apart from their isolation requirements, this function
    will pass on them as well.

    Parameters
    ---------
    seed : str
        Name of the seed which is checked for its 'backup seed' properties
    precale : int
        Prescale value for 'seed'
    otherseed : str
        Name of the algorithm which 'seed' is checked against
    otherprescale : int
        Prescale value for 'otherseed'

    Returns
    -------
    (bool, str)
        True if 'seed' is a backup seed to 'otherseed' or False otherwise,
        the name of the other seed if 'otherseed' is a signal seed to 'seed' or
        None otherwise, the name of the criterion (None if 'seed' is not a
        backup seed)

    """

    is_backup_candidate = False

    seed_basename = get_seed_basename(seed)
    otherseed_basename = get_seed_basename(otherseed)

    # skip if different events alltogether
    if seed_basename != otherseed_basename:
        return False, None, None

    # do not process further if there are multiple isolation criteria in a seed
    pattern = r'Iso|LooseIso'
    if any([len(re.findall(pattern, s)) > 1 for s in (seed, otherseed)]):
        return False, None, None

    # do not process further if neither seed has an isolation restriction
    if all([len(re.findall(pattern, s)) == 0 for s in (seed, otherseed)]):
        return False, None, None

    # extract the isolation substring from 'seed'
    seed_iso_str = re.search(pattern, seed)
    if seed_iso_str:
        seed_iso_str = seed_iso_str.group(0)
        seed_stripped = seed.replace(seed_iso_str,'')
        if seed_stripped.endswith('_'): seed_stripped = seed_stripped[:-1]

    else:
        seed_stripped = seed

    # extract the iso restriction substring from 'otherseed'
    otherseed_iso_str = re.search(pattern, otherseed)
    if otherseed_iso_str:
        otherseed_iso_str = otherseed_iso_str.group(0)
        otherseed_stripped = otherseed.replace(otherseed_iso_str,'')
        if otherseed_stripped.endswith('_'): otherseed_stripped = otherseed_stripped[:-1]

    else:
        otherseed_stripped = otherseed

    # do not process further if the seeds are different (apart from their
    # isolation criteria)
    if seed_stripped != otherseed_stripped:
        return False, None, None

    if seed_iso_str == 'Iso' and otherseed_iso_str == 'LooseIso':
        is_backup_candidate = True

    if seed_iso_str == 'Iso' and otherseed_iso_str is None:
        is_backup_candidate = True

    if seed_iso_str == 'LooseIso' and otherseed_iso_str is None:
        is_backup_candidate = True

    return is_backup_candidate, (otherseed if is_backup_candidate else None), \
            ('isolation' if is_backup_candidate else None)


if __name__ == '__main__':
    print('\n*** WARNING: This script is under development. Use with caution! ***\n')

    parser = argparse.ArgumentParser()
    parser.add_argument('filename',
            help='Name/path of the PS table file',
            type=str)

    args = parser.parse_args()

    table = read_table(args.filename)
    signal_seeds, backup_seeds = separate_signal_and_backup_seeds(table)

    signal_seeds.to_csv('signal_seeds.csv')
    backup_seeds.to_csv('backup_seeds.csv')
