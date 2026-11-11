"""单位与容量口径换算（零依赖，仅 Python 标准库）。

本模块只做纯量纲换算，不含任何业务逻辑，也不内置任何实时汇率：

* 容量：MW <-> kW（×1000 / ÷1000）。
* 价格：/MW <-> /kW（÷1000 / ×1000）、/day <-> /year（×days / ÷days，
  ``days`` 默认 365，与 SKILL.md 中 PJM「×365」口径一致，但可显式覆盖）。
* 通用容量价换算尺 ``convert_capacity_price``：支持
  ``$/MW-day``、``$/MW-yr``、``$/kW-yr``、``€/MW-yr``、``€/kW-yr``、
  ``PLN/MW-yr``、``PLN/kW-yr``、``£/MW-yr``、``£/kW-yr``、
  ``¥/MW-yr``、``¥/kW-yr``、``¥/kW``（后两者为中国容量年价「元/kW·年」
  的写法，按人民币 CNY 口径）。跨币种换算的汇率必须由 ``fx_to_usd``
  显式传入（每 1 单位该币种 = 多少 USD），未传则抛 ValueError；同币种
  换算不需要汇率，断言只验证纯数学关系（×1000、×365、÷1000）。

重要口径边界：法国 PL-1 的 ``€/MW`` 是「每 MW 每交付期」的清算价，
**不是年价**，故故意不纳入本换算尺，禁止通过 ×365 或 365/151 年化；
交付期折算见 ``capacity.py``。SKILL.md 明确「不得把交付期价直接年化」。

所有算例均为合成/演示口径。
"""

from __future__ import annotations


# 单位 -> (币种, 乘数)：乘以该乘数得到「本币 / kW·年」。
# 仅收录年价/日价单位；交付期价 €/MW 不在其中（见模块 docstring）。
# ``¥`` 按人民币容量年价口径，若需日元请自行以显式汇率映射。
_UNIT_SPECS = {
    "$/MW-day": ("USD", None),          # 乘数 = days/1000，运行时按 days 计算
    "$/MW-yr": ("USD", 1.0 / 1000.0),
    "$/kW-yr": ("USD", 1.0),
    "€/MW-yr": ("EUR", 1.0 / 1000.0),
    "€/kW-yr": ("EUR", 1.0),
    "PLN/MW-yr": ("PLN", 1.0 / 1000.0),
    "PLN/kW-yr": ("PLN", 1.0),
    "£/MW-yr": ("GBP", 1.0 / 1000.0),
    "£/kW-yr": ("GBP", 1.0),
    "¥/MW-yr": ("CNY", 1.0 / 1000.0),
    "¥/kW-yr": ("CNY", 1.0),
    "¥/kW": ("CNY", 1.0),
}

_DAY_UNIT = "$/MW-day"


def mw_to_kw(mw):
    """容量 MW -> kW（1 MW = 1000 kW）。

    口径：铭牌容量 / 降额容量 / ELCC 容量均适用；用于把以 MW 计的容量
    换成以 kW 计（如英国 CM 按 de-rated kW 付钱）。
    """
    return mw * 1000.0


def kw_to_mw(kw):
    """容量 kW -> MW（1000 kW = 1 MW），与 :func:`mw_to_kw` 互逆。

    口径：容量单位互转，不改变容量口径（铭牌/降额/ELCC 不变）。
    """
    return kw / 1000.0


def price_per_mw_to_per_kw(price_per_mw):
    """单价 /MW -> /kW（÷1000），币种与计价周期不变。

    单位：入参为「每 MW 的价格」，返回「每 kW 的价格」。
    例：比利时 €27,300/MW·年 = €27.3/kW·年。
    """
    return price_per_mw / 1000.0


def price_per_kw_to_per_mw(price_per_kw):
    """单价 /kW -> /MW（×1000），币种与计价周期不变。

    单位：入参为「每 kW 的价格」，返回「每 MW 的价格」。
    例：英国 £27.10/kW·年 = £27,100/MW·年；波兰 465.02 PLN/kW·年
    对应 465,020 PLN/MW·年（与波兰容量收入公式的 ×1000 系数呼应）。
    """
    return price_per_kw * 1000.0


def per_day_to_per_year(price_per_day, days=365):
    """按日价 -> 按年价（×days）。

    单位：入参「每单位容量每天的价格」，返回「每单位容量每年的价格」。
    口径：仅当规则允许年化时使用；``days`` 默认 365（PJM BRA 的 365
    口径），可显式覆盖以避免写死。例：PJM $325/MW-day = $118,625/MW-年。
    """
    return price_per_day * days


def per_year_to_per_day(price_per_year, days=365):
    """按年价 -> 按日价（÷days），与 :func:`per_day_to_per_year` 互逆。

    单位：入参「每年价格」，返回「每天价格」；``days`` 默认 365。
    """
    return price_per_year / days


def mw_day_to_kw_year(price_usd_per_mw_day, days=365):
    """组合换算：$ /MW-day -> $ /kW-年（×days/1000）。

    口径：先按 ``days``（默认 365）年化、再把 MW 折成 kW，币种不变。
    例：PJM $325/MW-day = $118.625/kW-年。纯数学关系，不涉及汇率。
    """
    return price_usd_per_mw_day * days / 1000.0


def _fx_to_usd(currency, fx_to_usd):
    """取「1 单位该币种 = 多少 USD」的显式汇率。

    USD 固定为 1.0；其它币种若 ``fx_to_usd`` 未提供则抛 ValueError，
    以此强制「汇率必须显式传入、不写死实时汇率」的纪律。
    """
    if currency == "USD":
        return 1.0
    if fx_to_usd is None or currency not in fx_to_usd:
        raise ValueError(
            "跨币种换算必须显式提供 fx_to_usd['%s']（每 1 %s = 多少 USD）；"
            "本模块不内置任何实时汇率" % (currency, currency)
        )
    return fx_to_usd[currency]


def _factor(unit, days):
    """返回该单位 -> 「本币/kW·年」的乘数。

    日价单位 ``$/MW-day`` 的乘数按 ``days`` 动态计算，其它单位取常量。
    """
    currency, factor = _UNIT_SPECS[unit]
    if unit == _DAY_UNIT:
        return currency, days / 1000.0
    return currency, factor


def convert_capacity_price(value, from_unit, to_unit, fx_to_usd=None, days=365):
    """通用容量价换算尺：把 ``value`` 从 ``from_unit`` 换到 ``to_unit``。

    参数
    ----
    value : float
        待换算的价格数值（单位由 ``from_unit`` 给出）。
    from_unit, to_unit : str
        单位串，取值为 :func:`supported_units` 返回的键。
    fx_to_usd : dict, 可选
        「币种 -> 每 1 单位该币种等于多少 USD」的显式汇率表。同币种换算
        （如 €/MW-yr -> €/kW-yr）不需要汇率；跨币种换算必须显式提供，
        否则抛 ValueError。断言只验证纯数学关系与显式假汇率下的换算链。
    days : float, 可选
        日价年化天数，默认 365（PJM 口径），可显式覆盖以避免写死。

    口径边界
    --------
    本函数只处理年价/日价单位。法国 PL-1 的「€/MW 每交付期」清算价
    **不是年价**，不纳入换算尺，禁止年化；见 ``capacity.py``。
    """
    if from_unit not in _UNIT_SPECS:
        raise ValueError("未知单位: %r" % (from_unit,))
    if to_unit not in _UNIT_SPECS:
        raise ValueError("未知单位: %r" % (to_unit,))
    c1, f1 = _factor(from_unit, days)
    c2, f2 = _factor(to_unit, days)
    if c1 == c2:
        # 同币种：汇率约掉，纯数学关系，不依赖任何汇率。
        return value * f1 / f2
    usd_per_kw_year = value * f1 * _fx_to_usd(c1, fx_to_usd)
    return usd_per_kw_year / (f2 * _fx_to_usd(c2, fx_to_usd))


def supported_units():
    """返回换算尺支持的单位元组（便于自测枚举，口径见模块 docstring）。

    注意：法国交付期价 ``€/MW`` 被刻意排除，禁止通过本换算尺年化。
    """
    return tuple(_UNIT_SPECS.keys())
