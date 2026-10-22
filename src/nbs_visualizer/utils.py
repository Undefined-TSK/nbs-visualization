"""缓动函数、数学辅助工具。无外部依赖。"""

def css_bezier(t: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """CSS cubic-bezier 计时函数，精确匹配浏览器动画曲线。

    使用 Newton-Raphson 迭代求解 x(u)=t，返回 y(u)。
    支持超调（y1>1 或 y2>1 时 y 可超过 1.0）。
    """
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0

    u = t
    for _ in range(10):
        xu = 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u ** 3
        dxu = (3 * (1 - u) ** 2 * x1 + 6 * (1 - u) * u * (x2 - x1)
               + 3 * u * u * (1 - x2))
        if abs(dxu) < 1e-10:
            break
        diff = xu - t
        if abs(diff) < 1e-8:
            break
        u -= diff / dxu
        u = max(0.0, min(1.0, u))

    return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3


def ease_out_back(t: float) -> float:
    """cubic-bezier(0.34, 1.56, 0.64, 1) — 弹性超调回弹曲线。"""
    return css_bezier(t, 0.34, 1.56, 0.64, 1.0)


def ease_press(t: float) -> float:
    """cubic-bezier(0.25, 0.1, 0.25, 1) — 快速按下曲线。"""
    return css_bezier(t, 0.25, 0.1, 0.25, 1.0)


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_cubic(t: float) -> float:
    return t * t * t


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - (-2 * t + 2) ** 3 / 2


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lerp(a, b, t):
    return a + (b - a) * t
