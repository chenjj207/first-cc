# -*- coding: utf-8 -*-
"""生成软件图标 app.ico：一个带绿叶的红色番茄（纯 Python 绘制，无需第三方库）"""
import struct
import zlib

SIZE = 256


def feather(d, edge):
    """根据椭圆距离 d（0=中心，1=边缘）计算透明度，边缘做柔化"""
    if d <= 1.0:
        return 255
    if d <= edge:
        return int((edge - d) / (edge - 1.0) * 255)
    return 0


def ellipse(x, y, dx, dy, rx, ry):
    """点 (x,y) 到椭圆 (中心 dx,dy，半径 rx,ry) 的归一化距离平方"""
    return ((x - dx) / rx) ** 2 + ((y - dy) / ry) ** 2


rows = []
for y in range(SIZE):
    row = bytearray([0])  # PNG 每行第一个字节：滤波器类型 0
    for x in range(SIZE):
        r = g = b = a = 0

        # 番茄主体（略扁的红色椭圆）
        d_body = ellipse(x, y, 128, 142, 106, 96)
        # 高光（左上浅色椭圆）
        d_shine = ellipse(x, y, 96, 112, 34, 26)
        # 叶子（顶部两片绿椭圆）
        d_leaf1 = ellipse(x, y, 116, 50, 24, 13)
        d_leaf2 = ellipse(x, y, 142, 52, 22, 12)
        # 果柄
        d_stem = ellipse(x, y, 128, 38, 7, 10)

        if d_body <= 1.0:
            if d_shine <= 1.0:
                r, g, b = 240, 116, 92      # 高光色
            else:
                r, g, b = 232, 85, 59       # 主色 #E8553B
            a = 255
        elif d_body <= 1.15:
            r, g, b = 232, 85, 59
            a = feather(d_body, 1.15)

        # 叶子叠在番茄上方
        if d_leaf1 <= 1.0 or d_leaf2 <= 1.0:
            r, g, b = 79, 155, 95           # 叶绿 #4F9B5F
            a = 255
        if d_stem <= 1.0:
            r, g, b = 62, 124, 79           # 果柄深绿
            a = 255

        row += bytes((r, g, b, a))
    rows.append(bytes(row))

raw = b"".join(rows)


def chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


ihdr = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)  # 8bit RGBA
png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
       + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

# ICO 容器：直接内嵌 PNG（Windows Vista 及以上均支持）
ico_header = struct.pack("<HHH", 0, 1, 1)                       # 保留/类型/图像数
ico_entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32,        # 宽高 0=256px、32 位色
                        len(png), 22)                           # 数据大小/偏移
with open("app.ico", "wb") as f:
    f.write(ico_header + ico_entry + png)

print("app.ico 生成完毕，大小", len(ico_header + ico_entry + png), "字节")
