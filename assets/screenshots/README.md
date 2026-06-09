# Screenshots

公开展示用截图资产。当前为**占位图（placeholder）**，发布前请用真实页面截图替换，
文件名保持不变即可（README 已按这些路径引用）。

| 文件 | 来源页面 | 截图要点 |
|------|----------|----------|
| `dcf-dashboard.png` | `http://127.0.0.1:5000/modeling/dcf?symbol=AAPL` | 中文 DCF 估值工作台：公司信息 + 假设参数（WACC、终值方法、运营预测）。用公开 ticker（如 AAPL），**不要**用真实个人持仓。 |
| `lbo-formula-workbook.png` | 在 `http://127.0.0.1:5000/modeling/lbo` 运行后导出 LBO Excel，并在 Excel 中打开 | **必须**能看到**公式栏 / 单元格活公式**，体现 formula-native（而非写死数值）。**裁掉**本地文件路径、用户名等隐私信息。 |
| `ma-arena.png` | `http://127.0.0.1:5000/modeling/ma/arena` | 并购牌桌 + 公司牌堆（seed deck）+ 玩家手牌，体现游戏化、确定性并购推演。 |

## 捕获建议

- 视口宽度约 **1280px**，深色主题。
- 仅展示公开市场数据与产品 UI；**不要**包含真实个人持仓 / 成本 / 邮箱 / 绝对路径 / 本地用户名。
- 导出为 PNG，单张控制在合理大小（建议 < 500 KB）。
- 覆盖同名文件后，README 截图区会自动显示真实截图。
