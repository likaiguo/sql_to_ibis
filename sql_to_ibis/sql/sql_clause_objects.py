from dataclasses import dataclass
from typing import Optional, Union

from sql_to_ibis.sql.sql_value_objects import Column, JoinBase, Subquery, Table, Value


class RowRangeClause:
    _row = "ROW"
    _range = "RANGE"
    _clause_types = [_row, _range]

    def __init__(
        self,
        clause_type: str,
        preceding: Optional[Union[int, tuple]],
        following: Optional[Union[int, tuple]],
    ):
        if clause_type not in self._clause_types:
            raise Exception(f"Type must be one of {self._clause_types}")
        self.preceding = preceding
        self.following = following


@dataclass
class LimitExpression:
    limit: int


@dataclass
class ValueExpression:
    value: Value


@dataclass
class WhereExpression(ValueExpression):
    pass


@dataclass
class ColumnExpression:
    column: Column

    @property
    def column_value(self):
        return self.column.get_value()


@dataclass
class OrderByExpression(ColumnExpression):
    ascending: bool = True

    @property
    def column_value(self):
        column = self.column if self.ascending else self.column.desc()
        return column.get_value()


class PartitionByExpression(ColumnExpression):
    pass


@dataclass
class FromExpression:
    value: Union[Subquery, JoinBase, Table]


@dataclass
class AliasExpression:
    alias: str