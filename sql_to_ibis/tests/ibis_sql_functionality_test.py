"""
Test cases for panda to sql
"""
from datetime import date, datetime

import ibis
from ibis.expr.api import TableExpr

from freezegun import freeze_time
import numpy as np
from pandas import concat, merge
import pandas.testing as tm
import pytest

from sql_to_ibis import query, register_temp_table, remove_temp_table
from sql_to_ibis.exceptions.sql_exception import (
    TableExprDoesNotExist,
    InvalidQueryException,
)
from sql_to_ibis.sql_objects import AmbiguousColumn
from sql_to_ibis.sql_select_query import TableInfo
from sql_to_ibis.tests.utils import (
    AVOCADO,
    DIGIMON_MON_LIST,
    DIGIMON_MOVE_LIST,
    FOREST_FIRES,
    register_env_tables,
    remove_env_tables,
    assert_ibis_equal_show_diff,
    assert_state_not_change,
)


@pytest.fixture(autouse=True, scope="module")
def module_setup_teardown():
    register_env_tables()
    yield
    remove_env_tables()


def test_add_remove_temp_table():
    """
    Tests registering and removing temp tables
    :return:
    """
    frame_name = "digimon_mon_list"
    real_frame_name = TableInfo.ibis_table_name_map[frame_name]
    remove_temp_table(frame_name)
    tables_present_in_column_to_dataframe = set()
    for column in TableInfo.column_to_dataframe_name:
        table = TableInfo.column_to_dataframe_name[column]
        if isinstance(table, AmbiguousColumn):
            for table_name in table.tables:
                tables_present_in_column_to_dataframe.add(table_name)
        else:
            tables_present_in_column_to_dataframe.add(table)

    # Ensure column metadata is removed correctly
    assert (
        frame_name not in TableInfo.ibis_table_name_map
        and real_frame_name not in TableInfo.ibis_table_map
        and real_frame_name not in TableInfo.column_name_map
        and real_frame_name not in tables_present_in_column_to_dataframe
    )

    registered_frame_name = real_frame_name
    register_temp_table(DIGIMON_MON_LIST, registered_frame_name)

    assert (
        TableInfo.ibis_table_name_map.get(frame_name.lower()) == registered_frame_name
        and real_frame_name in TableInfo.column_name_map
    )

    assert_ibis_equal_show_diff(
        TableInfo.ibis_table_map[registered_frame_name], DIGIMON_MON_LIST
    )

    # Ensure column metadata is added correctly
    for column in DIGIMON_MON_LIST.columns:
        assert column == TableInfo.column_name_map[registered_frame_name].get(
            column.lower()
        )
        lower_column = column.lower()
        assert lower_column in TableInfo.column_to_dataframe_name
        table = TableInfo.column_to_dataframe_name.get(lower_column)
        if isinstance(table, AmbiguousColumn):
            assert registered_frame_name in table.tables
        else:
            assert registered_frame_name == table


@assert_state_not_change
def test_for_valid_query():
    """
    Test that exception is raised for invalid query
    :return:
    """
    sql = "hello world!"
    try:
        query(sql)
    except InvalidQueryException as err:
        assert isinstance(err, InvalidQueryException)


@assert_state_not_change
def test_select_star():
    """
    Tests the simple select * case
    :return:
    """
    my_frame = query("select * from forest_fires")
    ibis_table = FOREST_FIRES
    assert_ibis_equal_show_diff(my_frame, ibis_table)


@assert_state_not_change
def test_case_insensitivity():
    """
    Tests to ensure that the sql is case insensitive for table names
    :return:
    """
    my_frame = query("select * from FOREST_fires")
    ibis_table = FOREST_FIRES
    assert_ibis_equal_show_diff(my_frame, ibis_table)


@assert_state_not_change
def test_select_specific_fields():
    """
    Tests selecting specific fields
    :return:
    """
    my_frame = query("select temp, RH, wind, rain as water, area from forest_fires")

    ibis_table = FOREST_FIRES[["temp", "RH", "wind", "rain", "area"]].relabel(
        {"rain": "water"}
    )
    assert_ibis_equal_show_diff(my_frame, ibis_table)


@assert_state_not_change
def test_type_conversion():
    """
    Tests sql as statements
    :return:
    """
    my_frame = query(
        """select cast(temp as int64),
        cast(RH as float64) my_rh, 
        wind, 
        rain, 
        area,
        cast(2.0 as int64) my_int,
        cast(3 as float64) as my_float,
        cast(7 as object) as my_object,
        cast(0 as bool) as my_bool from forest_fires"""
    )
    fire_frame = FOREST_FIRES.projection(
        [
            FOREST_FIRES.temp.cast("int64").name("temp"),
            FOREST_FIRES.RH.cast("float64").name("my_rh"),
            FOREST_FIRES.wind,
            FOREST_FIRES.rain,
            FOREST_FIRES.area,
            ibis.literal(2.0).cast("int64").name("my_int"),
            ibis.literal(3).cast("float64").name("my_float"),
            ibis.literal(7).cast("string").name("my_object"),
            ibis.literal(0).cast("bool").name("my_bool"),
        ]
    )
    assert_ibis_equal_show_diff(fire_frame, my_frame)


@assert_state_not_change
def test_for_non_existent_table():
    """
    Check that exception is raised if table does not exist
    :return:
    """
    try:
        query("select * from a_table_that_is_not_here")
    except Exception as err:
        assert isinstance(err, TableExprDoesNotExist)


@assert_state_not_change
def test_using_math():
    """
    Test the mathematical operations and order of operations
    :return:
    """
    my_frame = query("select temp, 1 + 2 * 3 as my_number from forest_fires")
    ibis_table = FOREST_FIRES[["temp"]]
    ibis_table = ibis_table.mutate(
        (ibis.literal(1) + ibis.literal(2) * ibis.literal(3)).name("my_number")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_distinct():
    """
    Test use of the distinct keyword
    :return:
    """
    my_frame = query("select distinct area, rain from forest_fires")
    ibis_table = FOREST_FIRES[["area", "rain"]].distinct()
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_columns_maintain_order_chosen():
    my_frame = query("select area, rain from forest_fires")
    ibis_table = FOREST_FIRES[["area", "rain"]]
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_subquery():
    """
    Test ability to perform subqueries
    :return:
    """
    my_frame = query("select * from (select area, rain from forest_fires) rain_area")
    ibis_table = FOREST_FIRES[["area", "rain"]]
    assert_ibis_equal_show_diff(ibis_table, my_frame)


# @assert_state_not_change
# def test_join_no_inner():
#     """
#     Test join
#     :return:
#     """
#     my_frame = query(
#         """select * from digimon_mon_list join
#             digimon_move_list
#             on digimon_mon_list.attribute = digimon_move_list.attribute"""
#     )
#     ibis_table1 = DIGIMON_MON_LIST
#     ibis_table2 = DIGIMON_MOVE_LIST
#     ibis_table = ibis_table1.merge(ibis_table2, on="Attribute")
#     assert_ibis_equal_show_diff(ibis_table, my_frame)


# @assert_state_not_change
# def test_join_wo_specifying_table():
#     """
#     Test join where table isn't specified in join
#     :return:
#     """
#     my_frame = query(
#         """
#         select * from digimon_mon_list join
#         digimon_move_list
#         on mon_attribute = move_attribute
#         """
#     )
#     ibis_table1 = DIGIMON_MON_LIST
#     ibis_table2 = DIGIMON_MOVE_LIST
#     ibis_table = ibis_table1.merge(
#         ibis_table2, left_on="mon_attribute", right_on="move_attribute"
#     )
#     assert_ibis_equal_show_diff(ibis_table, my_frame)
#
#
# @assert_state_not_change
# def test_join_w_inner():
#     """
#     Test join
#     :return:
#     """
#     my_frame = query(
#         """select * from digimon_mon_list inner join
#             digimon_move_list
#             on digimon_mon_list.attribute = digimon_move_list.attribute"""
#     )
#     ibis_table1 = DIGIMON_MON_LIST
#     ibis_table2 = DIGIMON_MOVE_LIST
#     ibis_table = ibis_table1.merge(ibis_table2, on="Attribute")
#     assert_ibis_equal_show_diff(ibis_table, my_frame)
#
#
# @assert_state_not_change
# def test_outer_join_no_outer():
#     """
#     Test outer join
#     :return:
#     """
#     my_frame = query(
#         """select * from digimon_mon_list full outer join
#             digimon_move_list
#             on digimon_mon_list.type = digimon_move_list.type"""
#     )
#     ibis_table1 = DIGIMON_MON_LIST
#     ibis_table2 = DIGIMON_MOVE_LIST
#     ibis_table = ibis_table1.merge(ibis_table2, how="outer", on="Type")
#     assert_ibis_equal_show_diff(ibis_table, my_frame)
#
#
# @assert_state_not_change
# def test_outer_join_w_outer():
#     """
#     Test outer join
#     :return:
#     """
#     my_frame = query(
#         """select * from digimon_mon_list full join
#             digimon_move_list
#             on digimon_mon_list.type = digimon_move_list.type"""
#     )
#     ibis_table1 = DIGIMON_MON_LIST
#     ibis_table2 = DIGIMON_MOVE_LIST
#     ibis_table = ibis_table1.merge(ibis_table2, how="outer", on="Type")
#     assert_ibis_equal_show_diff(ibis_table, my_frame)
#
#
# @assert_state_not_change
# def test_left_joins():
#     """
#     Test right, left, inner, and outer joins
#     :return:
#     """
#     my_frame = query(
#         """select * from digimon_mon_list left join
#             digimon_move_list
#             on digimon_mon_list.type = digimon_move_list.type"""
#     )
#     ibis_table1 = DIGIMON_MON_LIST
#     ibis_table2 = DIGIMON_MOVE_LIST
#     ibis_table = ibis_table1.merge(ibis_table2, how="left", on="Type")
#     assert_ibis_equal_show_diff(ibis_table, my_frame)
#
#
# @assert_state_not_change
# def test_left_outer_joins():
#     """
#     Test right, left, inner, and outer joins
#     :return:
#     """
#     my_frame = query(
#         """select * from digimon_mon_list left outer join
#             digimon_move_list
#             on digimon_mon_list.type = digimon_move_list.type"""
#     )
#     ibis_table1 = DIGIMON_MON_LIST
#     ibis_table2 = DIGIMON_MOVE_LIST
#     ibis_table = ibis_table1.merge(ibis_table2, how="left", on="Type")
#     assert_ibis_equal_show_diff(ibis_table, my_frame)
#
#
# @assert_state_not_change
# def test_right_joins():
#     """
#     Test right, left, inner, and outer joins
#     :return:
#     """
#     my_frame = query(
#         """select * from digimon_mon_list right join
#             digimon_move_list
#             on digimon_mon_list.type = digimon_move_list.type"""
#     )
#     ibis_table1 = DIGIMON_MON_LIST
#     ibis_table2 = DIGIMON_MOVE_LIST
#     ibis_table = ibis_table1.merge(ibis_table2, how="right", on="Type")
#     assert_ibis_equal_show_diff(ibis_table, my_frame)
#
#
# @assert_state_not_change
# def test_right_outer_joins():
#     """
#     Test right, left, inner, and outer joins
#     :return:
#     """
#     my_frame = query(
#         """select * from digimon_mon_list right outer join
#             digimon_move_list
#             on digimon_mon_list.type = digimon_move_list.type"""
#     )
#     ibis_table1 = DIGIMON_MON_LIST
#     ibis_table2 = DIGIMON_MOVE_LIST
#     ibis_table = ibis_table1.merge(ibis_table2, how="right", on="Type")
#     assert_ibis_equal_show_diff(ibis_table, my_frame)
#
#
# @assert_state_not_change
# def test_cross_joins():
#     """
#     Test right, left, inner, and outer joins
#     :return:
#     """
#     my_frame = query(
#         """select * from digimon_mon_list cross join
#             digimon_move_list
#             on digimon_mon_list.type = digimon_move_list.type"""
#     )
#     ibis_table1 = DIGIMON_MON_LIST
#     ibis_table2 = DIGIMON_MOVE_LIST
#     ibis_table = ibis_table1.merge(ibis_table2, how="outer", on="Type")
#     assert_ibis_equal_show_diff(ibis_table, my_frame)
#
#
@assert_state_not_change
def test_group_by():
    """
    Test group by constraint
    :return:
    """
    my_frame = query("""select month, day from forest_fires group by month, day""")
    ibis_table = FOREST_FIRES[["month", "day"]].distinct()
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_avg():
    """
    Test the avg
    :return:
    """
    my_frame = query("select avg(temp) from forest_fires")
    ibis_table = FOREST_FIRES.aggregate(
        [FOREST_FIRES.get_column("temp").mean().name("_col0")]
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_sum():
    """
    Test the sum
    :return:
    """
    my_frame = query("select sum(temp) from forest_fires")
    ibis_table = FOREST_FIRES.aggregate(
        [FOREST_FIRES.get_column("temp").sum().name("_col0")]
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_max():
    """
    Test the max
    :return:
    """
    my_frame = query("select max(temp) from forest_fires")
    ibis_table = FOREST_FIRES.aggregate(
        [FOREST_FIRES.get_column("temp").max().name("_col0")]
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_min():
    """
    Test the min
    :return:
    """
    my_frame = query("select min(temp) from forest_fires")
    ibis_table = FOREST_FIRES.aggregate(
        [FOREST_FIRES.get_column("temp").min().name("_col0")]
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_multiple_aggs():
    """
    Test multiple aggregations
    :return:
    """
    my_frame = query(
        "select min(temp), max(temp), avg(temp), max(wind) from forest_fires"
    )
    temp_column = FOREST_FIRES.get_column("temp")
    ibis_table = FOREST_FIRES.aggregate(
        [
            temp_column.min().name("_col0"),
            temp_column.max().name("_col1"),
            temp_column.mean().name("_col2"),
            FOREST_FIRES.get_column("wind").max().name("_col3"),
        ]
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_agg_w_groupby():
    """
    Test using aggregates and group by together
    :return:
    """
    my_frame = query(
        "select min(temp), max(temp) from forest_fires group by day, month"
    )
    temp_column = FOREST_FIRES.get_column("temp")
    ibis_table = FOREST_FIRES.group_by(["day", "month"]).aggregate(
        [temp_column.min().name("_col0"), temp_column.max().name("_col1")]
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_where_clause():
    """
    Test where clause
    :return:
    """
    my_frame = query("""select * from forest_fires where month = 'mar'""")
    ibis_table = FOREST_FIRES[FOREST_FIRES.month == "mar"]
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_all_boolean_ops_clause():
    """
    Test where clause
    :return:
    """
    my_frame = query(
        """select * from forest_fires where month = 'mar' and temp > 8.0 and rain >= 0
        and area != 0 and dc < 100 and ffmc <= 90.1
        """
    )
    ibis_table = FOREST_FIRES[
        (FOREST_FIRES.month == "mar")
        & (FOREST_FIRES.temp > 8.0)
        & (FOREST_FIRES.rain >= 0)
        & (FOREST_FIRES.area != ibis.literal(0))
        & (FOREST_FIRES.DC < 100)
        & (FOREST_FIRES.FFMC <= 90.1)
    ]
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_order_by():
    """
    Test order by clause
    :return:
    """
    my_frame = query(
        """select * from forest_fires order by temp desc, wind asc, area"""
    )
    ibis_table = FOREST_FIRES.sort_by([("temp", False), ("wind", True), ("area", True)])
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_limit():
    """
    Test limit clause
    :return:
    """
    my_frame = query("""select * from forest_fires limit 10""")
    ibis_table = FOREST_FIRES.head(10)
    assert_ibis_equal_show_diff(ibis_table, my_frame)


# # # TODO Add in parentheses support for Order of ops
@assert_state_not_change
def test_having_multiple_conditions():
    """
    Test having clause
    :return:
    """
    my_frame = query(
        "select min(temp) from forest_fires having min(temp) > 2 and "
        "max(dc) < 200 or month = 'oct'"
    )
    temp_column = FOREST_FIRES.get_column("temp")

    print(
        (temp_column.min() > 2) & (FOREST_FIRES.get_column("DC").max() < 200)
        | (FOREST_FIRES.get_column("month") == "oct")
    )
    ibis_table = FOREST_FIRES.aggregate(
        metrics=temp_column.min().name("_col0"), having=(),
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_having_one_condition():
    """
    Test having clause
    :return:
    """
    my_frame = query("select min(temp) from forest_fires having min(temp) > 2")
    ibis_table = FOREST_FIRES.copy()
    ibis_table["_col0"] = FOREST_FIRES["temp"]
    aggregated_df = ibis_table.aggregate({"_col0": "min"}).to_frame().transpose()
    ibis_table = aggregated_df[aggregated_df["_col0"] > 2]
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_having_with_group_by():
    """
    Test having clause
    :return:
    """
    my_frame = query(
        "select min(temp) from forest_fires group by day having min(temp) > 5"
    )
    ibis_table = (
        FOREST_FIRES.groupby("day")
        .having(FOREST_FIRES.temp.min() > 5)
        .aggregate(FOREST_FIRES.temp.min())
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_operations_between_columns_and_numbers():
    """
    Tests operations between columns
    :return:
    """
    my_frame = query("""select temp * wind + rain / dmc + 37 from forest_fires""")
    ibis_table = FOREST_FIRES.mutate(
        (
            FOREST_FIRES.temp * FOREST_FIRES.wind
            + FOREST_FIRES.rain / FOREST_FIRES.DMC
            + 37
        ).name("_col0")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_select_star_from_multiple_tables():
    """
    Test selecting from two different tables
    :return:
    """
    my_frame = query("""select * from forest_fires, digimon_mon_list""")
    ibis_table = FOREST_FIRES.cross_join(DIGIMON_MON_LIST)
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_select_columns_from_two_tables_with_same_column_name():
    """
    Test selecting tables
    :return:
    """
    my_frame = query("""select * from forest_fires table1, forest_fires table2""")
    ibis_table = FOREST_FIRES.cross_join(FOREST_FIRES)
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_maintain_case_in_query():
    """
    Test nested subqueries
    :return:
    """
    my_frame = query("""select wind, rh from forest_fires""")
    ibis_table = FOREST_FIRES[["wind", "RH"]].relabel({"RH": "rh"})
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_nested_subquery():
    """
    Test nested subqueries
    :return:
    """
    my_frame = query(
        """select * from
            (select wind, rh from
              (select * from forest_fires) fires) wind_rh"""
    )
    ibis_table = FOREST_FIRES[["wind", "RH"]].relabel({"RH": "rh"})
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_union():
    """
    Test union in queries
    :return:
    """
    my_frame = query(
        """
    select * from forest_fires order by wind desc limit 5
    union
    select * from forest_fires order by wind asc limit 5
    """
    )
    ibis_table1 = FOREST_FIRES.sort_by(("wind", False)).head(5)
    ibis_table2 = FOREST_FIRES.sort_by(("wind", True)).head(5)
    ibis_table = ibis_table1.union(ibis_table2, distinct=True)
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_union_distinct():
    """
    Test union distinct in queries
    :return:
    """
    my_frame = query(
        """
        select * from forest_fires order by wind desc limit 5
         union distinct
        select * from forest_fires order by wind asc limit 5
        """
    )
    ibis_table1 = FOREST_FIRES.sort_by(("wind", False)).head(5)
    ibis_table2 = FOREST_FIRES.sort_by(("wind", True)).head(5)
    ibis_table = ibis_table1.union(ibis_table2, distinct=True)
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_union_all():
    """
    Test union distinct in queries
    :return:
    """
    my_frame = query(
        """
        select * from forest_fires order by wind desc limit 5
         union all
        select * from forest_fires order by wind asc limit 5
        """
    )
    ibis_table1 = FOREST_FIRES.sort_by(("wind", False)).head(5)
    ibis_table2 = FOREST_FIRES.sort_by(("wind", True)).head(5)
    ibis_table = ibis_table1.union(ibis_table2)
    assert_ibis_equal_show_diff(ibis_table, my_frame)


# TODO No ibis intersect method!
@assert_state_not_change
def test_intersect_distinct():
    """
    Test union distinct in queries
    :return:
    """
    my_frame = query(
        """
            select * from forest_fires order by wind desc limit 5
             intersect distinct
            select * from forest_fires order by wind desc limit 3
            """
    )
    ibis_table1 = FOREST_FIRES.sort_by(("wind", False)).head(5)
    ibis_table2 = FOREST_FIRES.sort_by(("wind", True)).head(5)
    ibis_table = ibis_table1.union(ibis_table2, distinct=True)
    assert_ibis_equal_show_diff(ibis_table, my_frame)


# TODO No ibis except method!
@assert_state_not_change
def test_except_distinct():
    """
    Test except distinct in queries
    :return:
    """
    my_frame = query(
        """
                select * from forest_fires order by wind desc limit 5
                 except distinct
                select * from forest_fires order by wind desc limit 3
                """
    )
    ibis_table1 = (
        FOREST_FIRES.copy().sort_values(by=["wind"], ascending=[False]).head(5)
    )
    ibis_table2 = (
        FOREST_FIRES.copy().sort_values(by=["wind"], ascending=[False]).head(3)
    )
    ibis_table = (
        ibis_table1[~ibis_table1.isin(ibis_table2).all(axis=1)]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


# TODO No ibis except method!
@assert_state_not_change
def test_except_all():
    """
    Test except distinct in queries
    :return:
    """
    my_frame = query(
        """
                select * from forest_fires order by wind desc limit 5
                 except all
                select * from forest_fires order by wind desc limit 3
                """
    )
    ibis_table1 = (
        FOREST_FIRES.copy().sort_values(by=["wind"], ascending=[False]).head(5)
    )
    ibis_table2 = (
        FOREST_FIRES.copy().sort_values(by=["wind"], ascending=[False]).head(3)
    )
    ibis_table = ibis_table1[~ibis_table1.isin(ibis_table2).all(axis=1)].reset_index(
        drop=True
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_between_operator():
    """
    Test using between operator
    :return:
    """
    my_frame = query(
        """
    select * from forest_fires
    where wind between 5 and 6
    """
    )
    ibis_table = FOREST_FIRES.filter(FOREST_FIRES.wind.between(5, 6))
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_in_operator():
    """
    Test using in operator in a sql query
    :return:
    """
    my_frame = query(
        """
    select * from forest_fires where day in ('fri', 'sun')
    """
    )
    ibis_table = FOREST_FIRES[
        FOREST_FIRES.day.isin([ibis.literal("fri"), ibis.literal("sun")])
    ]
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_in_operator_expression_numerical():
    """
    Test using in operator in a sql query
    :return:
    """
    my_frame = query(
        """
    select * from forest_fires where X in (5, 9)
    """
    )
    ibis_table = FOREST_FIRES[FOREST_FIRES.X.isin((ibis.literal(5), ibis.literal(9)))]
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_not_in_operator():
    """
    Test using in operator in a sql query
    :return:
    """
    my_frame = query(
        """
    select * from forest_fires where day not in ('fri', 'sun')
    """
    )
    ibis_table = FOREST_FIRES[
        FOREST_FIRES.day.notin([ibis.literal("fri"), ibis.literal("sun")])
    ]
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_case_statement_w_name():
    """
    Test using case statements
    :return:
    """
    my_frame = query(
        """
        select case when wind > 5 then 'strong'
        when wind = 5 then 'mid'
        else 'weak' end as wind_strength
        from
        forest_fires
        """
    )
    ibis_table = FOREST_FIRES.mutate(
        ibis.case()
        .when(FOREST_FIRES.wind > 5, "strong")
        .when(FOREST_FIRES.wind == 5, "mid")
        .else_("weak")
        .end()
        .name("wind_strength")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_case_statement_w_no_name():
    """
    Test using case statements
    :return:
    """
    my_frame = query(
        """
        select case when wind > 5 then 'strong' when wind = 5 then 'mid' else 'weak' end
        from forest_fires
        """
    )
    ibis_table = FOREST_FIRES.mutate(
        ibis.case()
        .when(FOREST_FIRES.wind > 5, "strong")
        .when(FOREST_FIRES.wind == 5, "mid")
        .else_("weak")
        .end()
        .name("_col0")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_case_statement_w_other_columns_as_result():
    """
    Test using case statements
    :return:
    """
    my_frame = query(
        """
        select case when wind > 5 then month when wind = 5 then 'mid' else day end
        from forest_fires
        """
    )
    ibis_table = FOREST_FIRES.mutate(
        ibis.case()
        .when(FOREST_FIRES.wind > 5, FOREST_FIRES.month)
        .when(FOREST_FIRES.wind == 5, "mid")
        .else_(FOREST_FIRES.day)
        .end()
        .name("_col0")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


# TODO Ibis is showing window as object in string representation
@assert_state_not_change
def test_rank_statement_one_column():
    """
    Test rank statement
    :return:
    """
    my_frame = query(
        """
    select wind, rank() over(order by wind) as wind_rank
    from forest_fires
    """
    )
    ibis_table = FOREST_FIRES[["wind"]].mutate(
        FOREST_FIRES.wind.rank()
        .over(ibis.window(order_by=[FOREST_FIRES.wind]))
        .name("wind_rank")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_rank_statement_many_columns():
    """
    Test rank statement
    :return:
    """
    my_frame = query(
        """
    select wind, rain, month, rank() over(order by wind desc, rain asc, month) as rank
    from forest_fires
    """
    )
    ibis_table: TableExpr = FOREST_FIRES[["wind", "rain", "month"]]
    ibis_table = ibis_table.mutate(
        FOREST_FIRES.wind.rank()
        .over(
            ibis.window(
                order_by=[
                    ibis.desc(FOREST_FIRES.wind),
                    FOREST_FIRES.rain,
                    FOREST_FIRES.month,
                ]
            )
        )
        .name("rank")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_dense_rank_statement_many_columns():
    """
    Test dense_rank statement
    :return:
    """
    my_frame = query(
        """
    select wind, rain, month,
    dense_rank() over(order by wind desc, rain asc, month) as rank
    from forest_fires
    """
    )
    ibis_table = FOREST_FIRES[["wind", "rain", "month"]]
    ibis_table = ibis_table.mutate(
        FOREST_FIRES.wind.dense_rank()
        .over(
            ibis.window(
                order_by=[
                    ibis.desc(FOREST_FIRES.wind),
                    FOREST_FIRES.rain,
                    FOREST_FIRES.month,
                ]
            )
        )
        .name("rank")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_rank_over_partition_by():
    """
    Test rank partition by statement
    :return:
    """
    my_frame = query(
        """
    select wind, rain, month, day,
    rank() over(partition by day order by wind desc, rain asc, month) as rank
    from forest_fires
    """
    )
    ibis_table = FOREST_FIRES[["wind", "rain", "month", "day"]]
    ibis_table = ibis_table.mutate(
        FOREST_FIRES.wind.rank()
        .over(
            ibis.window(
                order_by=[
                    ibis.desc(FOREST_FIRES.wind),
                    FOREST_FIRES.rain,
                    FOREST_FIRES.month,
                ],
                group_by=[FOREST_FIRES.day],
            )
        )
        .name("rank")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_dense_rank_over_partition_by():
    """
    Test rank partition by statement
    :return:
    """
    my_frame = query(
        """
    select wind, rain, month, day,
    dense_rank() over(partition by day order by wind desc, rain asc, month) as rank
    from forest_fires
    """
    )
    ibis_table = FOREST_FIRES[["wind", "rain", "month", "day"]]
    ibis_table = ibis_table = ibis_table.mutate(
        FOREST_FIRES.wind.dense_rank()
        .over(
            ibis.window(
                order_by=[
                    ibis.desc(FOREST_FIRES.wind),
                    FOREST_FIRES.rain,
                    FOREST_FIRES.month,
                ],
                group_by=[FOREST_FIRES.day],
            )
        )
        .name("rank")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_set_string_value_as_column_value():
    """
    Select a string like 'Yes' as a column value
    :return:
    """
    my_frame = query(
        """
    select wind, 'yes' as wind_yes from forest_fires"""
    )
    ibis_table = FOREST_FIRES[["wind"]].mutate(ibis.literal("yes").name("wind_yes"))
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_datetime_cast():
    """
    Select casting a string as a date
    :return:
    """
    my_frame = query(
        """
    select wind, cast('2019-01-01' as datetime64) as my_date from forest_fires"""
    )
    ibis_table = FOREST_FIRES[["wind"]].mutate(
        ibis.literal("2019-01-01").cast("timestamp").name("my_date")
    )
    print(ibis_table)
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_date_cast():
    """
    Select casting a string as a date
    :return:
    """
    my_frame = query(
        """
    select wind, cast('2019-01-01' as date) as my_date from forest_fires"""
    )
    ibis_table = FOREST_FIRES[["wind"]].mutate(
        ibis.literal("2019-01-01").cast("date").name("my_date")
    )
    print(ibis_table)
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_timestamps():
    """
    Select now() as date
    :return:
    """
    with freeze_time(datetime.now()):
        my_frame = query(
            """
        select wind, now(), today(), timestamp('2019-01-31', '23:20:32')
        from forest_fires"""
        )
        ibis_table = FOREST_FIRES[["wind"]].mutate(
            [
                ibis.literal(datetime.now()).name("now()"),
                ibis.literal(date.today()).name("today()"),
                ibis.literal(datetime(2019, 1, 31, 23, 20, 32)).name("_literal2"),
            ]
        )
        assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_case_statement_with_same_conditions():
    """
    Test using case statements
    :return:
    """
    my_frame = query(
        """
        select case when wind > 5 then month when wind > 5 then 'mid' else day end
        from forest_fires
        """
    )
    ibis_table = FOREST_FIRES.mutate(
        ibis.case()
        .when(FOREST_FIRES.wind > 5, FOREST_FIRES.month)
        .when(FOREST_FIRES.wind > 5, "mid")
        .else_(FOREST_FIRES.day)
        .end()
        .name("_col0")
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


# TODO In ibis can't name same column different things in projection
@assert_state_not_change
def test_multiple_aliases_same_column():
    """
    Test multiple aliases on the same column
    :return:
    """
    my_frame = query(
        """
        select wind as my_wind, wind as also_the_wind, wind as yes_wind
        from
        forest_fires
        """
    )
    wind_column = FOREST_FIRES.get_column("wind")
    ibis_table = FOREST_FIRES.mutate(
        [
            wind_column.name("my_wind"),
            wind_column.name("also_the_wind"),
            wind_column.name("yes_wind"),
        ]
    )
    print(ibis_table)
    raise Exception
    assert_ibis_equal_show_diff(ibis_table, my_frame)


@assert_state_not_change
def test_sql_data_types():
    """
    Tests sql data types
    :return:
    """
    my_frame = query(
        """
        select
            cast(avocado_id as object) as avocado_id_object,
            cast(avocado_id as int16) as avocado_id_int16,
            cast(avocado_id as smallint) as avocado_id_smallint,
            cast(avocado_id as int32) as avocado_id_int32,
            cast(avocado_id as int) as avocado_id_int,
            cast(avocado_id as int64) as avocado_id_int64,
            cast(avocado_id as bigint) as avocado_id_bigint,
            cast(avocado_id as float) as avocado_id_float,
            cast(avocado_id as float16) as avocado_id_float16,
            cast(avocado_id as float32) as avocado_id_float32,
            cast(avocado_id as float64) as avocado_id_float64,
            cast(avocado_id as bool) as avocado_id_bool,
            cast(avocado_id as category) as avocado_id_category,
            cast(date as date) as date,
            cast(date as datetime64) as datetime,
            cast(date as timestamp) as timestamp,
            cast(date as time) as time,
            cast(region as varchar) as region_varchar,
            cast(region as string) as region_string
        from avocado
        """
    )

    date_column = AVOCADO.Date
    id_column = AVOCADO.avocado_id
    region_column = AVOCADO.region
    ibis_table = AVOCADO.projection(
        [
            id_column.cast("string").name("avocado_id_object"),
            id_column.cast("int16").name("avocado_id_int16"),
            id_column.cast("int16").name("avocado_id_smallint"),
            id_column.cast("int32").name("avocado_id_int32"),
            id_column.cast("int32").name("avocado_id_int"),
            id_column.cast("int64").name("avocado_id_int64"),
            id_column.cast("int64").name("avocado_id_bigint"),
            id_column.cast("float").name("avocado_id_float"),
            id_column.cast("float16").name("avocado_id_float16"),
            id_column.cast("float32").name("avocado_id_float32"),
            id_column.cast("float64").name("avocado_id_float64"),
            id_column.cast("bool").name("avocado_id_bool"),
            id_column.cast("string").name("avocado_id_category"),
            date_column.cast("date").name("date"),
            date_column.cast("timestamp").name("datetime"),
            date_column.cast("timestamp").name("timestamp"),
            date_column.cast("time").name("time"),
            region_column.cast("string").name("region_varchar"),
            region_column.cast("string").name("region_string"),
        ]
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


def test_math_order_of_operations_no_parens():
    """
    Test math parentheses
    :return:
    """

    my_frame = query("select 20 * avocado_id + 3 / 20 as my_math from avocado")

    ibis_table = AVOCADO.projection(
        [
            (
                ibis.literal(20) * AVOCADO.avocado_id
                + ibis.literal(3) / ibis.literal(20)
            ).name("my_math")
        ]
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


def test_math_order_of_operations_with_parens():
    """
    Test math parentheses
    :return:
    """

    my_frame = query(
        "select 20 * (avocado_id + 3) / (20 + avocado_id) as my_math from avocado"
    )
    avocado_id = AVOCADO.avocado_id
    ibis_table = AVOCADO.projection(
        [
            (
                ibis.literal(20)
                * (avocado_id + ibis.literal(3))
                / (ibis.literal(20) + avocado_id)
            ).name("my_math")
        ]
    )
    assert_ibis_equal_show_diff(ibis_table, my_frame)


def test_boolean_order_of_operations_with_parens():
    """
    Test boolean order of operations with parentheses
    :return:
    """
    my_frame = query(
        "select * from forest_fires "
        "where (month = 'oct' and day = 'fri') or "
        "(month = 'nov' and day = 'tue')"
    )

    ibis_table = FOREST_FIRES[
        ((FOREST_FIRES.month == "oct") & (FOREST_FIRES.day == "fri"))
        | ((FOREST_FIRES.month == "nov") & (FOREST_FIRES.day == "tue"))
    ]

    assert_ibis_equal_show_diff(ibis_table, my_frame)


if __name__ == "__main__":
    register_env_tables()
    test_type_conversion()
    remove_env_tables()
