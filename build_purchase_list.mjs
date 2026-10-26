import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputPath = "D:\\毕子扬的日常\\🛠 项目\\嵌赛项目购买清单.xlsx";
const previewPath = "C:\\Users\\39909\\Desktop\\FPGA\\tmp\\嵌赛项目购买清单预览.png";
const evidencePreviewPath = "C:\\Users\\39909\\Desktop\\FPGA\\tmp\\嵌赛项目购买清单截图预览.png";
const assetDir = "D:\\毕子扬的日常\\🛠 项目\\嵌赛项目购买清单.assets";
const fontFamily = "Aptos";

const orders = [
  [1, "霍尔编码器 TT 马达", "塑料轴，减速比 1:48，x2", "松甲科技机器人商城", "待发货", 28.8, "毕子扬", "待AA", "3316423191068019569", "商品总价 ¥30.00，运费 ¥3.80，店铺优惠 -¥5.00；预计后天 18 点前送达。", "c139d867226704af909660d98eff3dcb.png"],
  [2, "18650 锂电池充电器", "3.7V，插头双充，x1", "琦腾电子源头工厂", "已签收，待确认收货", 7.63, "毕子扬", "待AA", "3316385427313000388", "平台优惠 -¥2.26；2026-09-09 下单；东南大学园 2 舍东侧菜鸟驿站签收。", "439962cb323302016f17a067e8e7c34d.png"],
  [3, "18650 锂电池", "平头 4800mWh，2 节 + 赠 1 节，x1 套", "官方国货甄选", "交易成功", 11.36, "毕子扬", "待AA", "3316830781021091589", "2026-09-06 下单；防爆。", "b4d8547e30a8ffa75ba01b4c0e56aeab.png"],
  [4, "罗技 C270 高清摄像头", "C270，闲鱼购入，x1", "闲鱼", "已签收，待确认收货", 39, "毕子扬", "待AA", "3317006352284014759", "申通 772078957073642；2026-09-15 18:57:14 签收。", "44cef39403caff5a56b8eff9e5c42e40.png"],
  [5, "亚博智能 STM32 4WD 智能小车套件", "2022 年 11 月淘宝入，闲鱼购入，x1", "闲鱼", "交易成功", 180, "毕子扬", "待AA", "3316400330166041587", "已到达卖家账户。", "bb44ff96692df14a969037b1442d8761.png"],
];

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("购买清单");
const evidence = workbook.worksheets.add("截图凭证");

sheet.showGridLines = false;
evidence.showGridLines = false;

sheet.mergeCells("A1:J1");
sheet.getRange("A1").values = [["嵌赛项目购买清单"]];
sheet.mergeCells("A2:J2");
sheet.getRange("A2").values = [["记录元件采购、实付金额与 AA；后续新订单可继续追加。更新日期：2026-09-17"]];

sheet.mergeCells("A4:B4");
sheet.getRange("A4").values = [["当前汇总"]];
sheet.getRange("A5:B8").values = [
  ["已记录订单", null],
  ["元件类别", null],
  ["已支付合计", null],
  ["AA状态", "待补充分摊成员"],
];
sheet.getRange("B5").formulas = [["=COUNTA(A11:A15)"]];
sheet.getRange("B6").formulas = [["=COUNTA(A11:A15)"]];
sheet.getRange("B7").formulas = [["=SUM(F11:F15)"]];

sheet.mergeCells("D4:E4");
sheet.getRange("D4").values = [["AA记录"]];
sheet.getRange("D5:E8").values = [
  ["参与人", "待补"],
  ["分摊规则", "待补"],
  ["已收款", 0],
  ["待收款", null],
];
sheet.getRange("E8").formulas = [["=B7-E7"]];

sheet.getRange("A10:J15").values = [
  ["序号", "物品", "规格 / 数量", "店铺 / 来源", "订单状态", "实付金额", "付款人", "AA状态", "订单号", "备注"],
  ...orders.map((row) => [...row.slice(0, 8), `\u200B${row[8]}`, row[9]]),
];
const table = sheet.tables.add("A10:J15", true, "PurchaseTable");
table.style = "TableStyleMedium2";
table.showFilterButton = true;

sheet.mergeCells("A18:J18");
sheet.getRange("A18").values = [["说明：金额均按订单页面显示的实付款记录，已包含截图中显示的优惠和运费。新截图请追加到“截图凭证”工作表。"]];

sheet.getRange("A1:J100").format.font = { name: fontFamily, size: 10, color: "#1F2937" };
sheet.getRange("A1:J100").format.verticalAlignment = "center";
sheet.getRange("A1:J1").format = { font: { name: fontFamily, size: 16, bold: true, color: "#17365D" }, horizontalAlignment: "left", rowHeight: 28 };
sheet.getRange("A2:J2").format = { font: { name: fontFamily, size: 10, italic: true, color: "#5B6573" }, horizontalAlignment: "left", rowHeight: 22 };
sheet.getRange("A4:B4").format = { fill: "#1F4E78", font: { name: fontFamily, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "left" };
sheet.getRange("D4:E4").format = { fill: "#1F4E78", font: { name: fontFamily, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "left" };
sheet.getRange("A5:A8").format = { fill: "#D9EAF7", font: { name: fontFamily, size: 10, bold: true, color: "#17365D" } };
sheet.getRange("D5:D8").format = { fill: "#D9EAF7", font: { name: fontFamily, size: 10, bold: true, color: "#17365D" } };
sheet.getRange("B7:B7").format.font = { name: fontFamily, size: 10, bold: true, color: "#17365D" };
sheet.getRange("E8:E8").format.font = { name: fontFamily, size: 10, bold: true, color: "#17365D" };
sheet.getRange("A10:J10").format = { fill: "#1F4E78", font: { name: fontFamily, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, rowHeight: 30 };
sheet.getRange("A11:J15").format.wrapText = true;
sheet.getRange("A11:J15").format.rowHeight = 42;
sheet.getRange("B11:C15").format.verticalAlignment = "top";
sheet.getRange("J11:J15").format.verticalAlignment = "top";
sheet.getRange("F11:F15").format.numberFormat = '"¥"#,##0.00';
sheet.getRange("B7:B7").format.numberFormat = '"¥"#,##0.00';
sheet.getRange("E7:E8").format.numberFormat = '"¥"#,##0.00';
sheet.getRange("E11:E15").format.horizontalAlignment = "center";
sheet.getRange("F11:F15").format.horizontalAlignment = "right";
sheet.getRange("H11:H15").format.horizontalAlignment = "center";
sheet.getRange("I11:I15").format.numberFormat = "@";
sheet.getRange("I11:I15").format.horizontalAlignment = "left";
sheet.getRange("A10:J15").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
sheet.getRange("A18:J18").format = { font: { name: fontFamily, size: 9, italic: true, color: "#5B6573" }, wrapText: true, rowHeight: 28 };
sheet.getRange("A1:A100").format.columnWidth = 7;
sheet.getRange("B1:B100").format.columnWidth = 25;
sheet.getRange("C1:C100").format.columnWidth = 31;
sheet.getRange("D1:D100").format.columnWidth = 23;
sheet.getRange("E1:E100").format.columnWidth = 20;
sheet.getRange("F1:F100").format.columnWidth = 12;
sheet.getRange("G1:G100").format.columnWidth = 12;
sheet.getRange("H1:H100").format.columnWidth = 11;
sheet.getRange("I1:I100").format.columnWidth = 21;
sheet.getRange("J1:J100").format.columnWidth = 43;
sheet.freezePanes.freezeRows(10);

evidence.mergeCells("A1:H1");
evidence.getRange("A1").values = [["截图凭证"]];
evidence.mergeCells("A2:H2");
evidence.getRange("A2").values = [["当前 5 笔采购的原始订单截图；后续新截图可继续追加。"]];
evidence.getRange("A4:G9").values = [
  ["序号", "物品", "实付金额", "订单状态", "订单号", "截图文件", "备注"],
  ...orders.map((row) => [row[0], row[1], row[5], row[4], `\u200B${row[8]}`, row[10], row[9]]),
];
const evidenceTable = evidence.tables.add("A4:G9", true, "EvidenceTable");
evidenceTable.style = "TableStyleMedium2";
evidenceTable.showFilterButton = true;
evidence.getRange("A1:H100").format.font = { name: fontFamily, size: 10, color: "#1F2937" };
evidence.getRange("A1:H100").format.verticalAlignment = "center";
evidence.getRange("A1:H1").format = { font: { name: fontFamily, size: 16, bold: true, color: "#17365D" }, horizontalAlignment: "left", rowHeight: 28 };
evidence.getRange("A2:H2").format = { font: { name: fontFamily, size: 10, italic: true, color: "#5B6573" }, horizontalAlignment: "left", rowHeight: 22 };
evidence.getRange("A4:G4").format = { fill: "#1F4E78", font: { name: fontFamily, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", wrapText: true, rowHeight: 30 };
evidence.getRange("A5:G9").format.wrapText = true;
evidence.getRange("A5:G9").format.rowHeight = 38;
evidence.getRange("C5:C9").format.numberFormat = '"¥"#,##0.00';
evidence.getRange("E5:E9").format.numberFormat = "@";
evidence.getRange("E5:E9").format.horizontalAlignment = "left";
evidence.getRange("A4:G9").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
evidence.getRange("A1:A100").format.columnWidth = 7;
evidence.getRange("B1:B100").format.columnWidth = 26;
evidence.getRange("C1:C100").format.columnWidth = 12;
evidence.getRange("D1:D100").format.columnWidth = 20;
evidence.getRange("E1:E100").format.columnWidth = 22;
evidence.getRange("F1:F100").format.columnWidth = 37;
evidence.getRange("G1:G100").format.columnWidth = 44;
evidence.getRange("H1:H100").format.columnWidth = 4;

const imagePlacements = [
  { index: 0, labelCell: "B12", anchor: { row: 11, col: 1 } },
  { index: 1, labelCell: "F12", anchor: { row: 11, col: 5 } },
  { index: 2, labelCell: "B45", anchor: { row: 44, col: 1 } },
  { index: 3, labelCell: "F45", anchor: { row: 44, col: 5 } },
  { index: 4, labelCell: "B78", anchor: { row: 77, col: 1 } },
];
for (const placement of imagePlacements) {
  const order = orders[placement.index];
  const labelRange = evidence.getRange(placement.labelCell);
  labelRange.values = [[`${order[0]}. ${order[1]} | 实付 ¥${order[5].toFixed(2)}`]];
  labelRange.format = { font: { name: fontFamily, size: 10, bold: true, color: "#17365D" }, wrapText: true, rowHeight: 24 };
  const bytes = await fs.readFile(`${assetDir}\\${order[10]}`);
  evidence.images.add({
    dataUrl: `data:image/png;base64,${bytes.toString("base64")}`,
    anchor: { from: placement.anchor, extent: { widthPx: 240, heightPx: 520 } },
  });
}
evidence.freezePanes.freezeRows(4);

workbook.recalculate();
const check = await workbook.inspect({ kind: "table", sheetId: "购买清单", range: "A1:J18", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 12, maxChars: 6000 });
console.log(check.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
console.log(errors.ndjson);

const preview = await workbook.render({ sheetName: "购买清单", range: "A1:J18", scale: 1, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
const evidencePreview = await workbook.render({ sheetName: "截图凭证", range: "A1:H110", scale: 0.7, format: "png" });
await fs.writeFile(evidencePreviewPath, new Uint8Array(await evidencePreview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const reloaded = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const savedCheck = await reloaded.inspect({ kind: "table", sheetId: "购买清单", range: "A1:J15", include: "values,formulas", tableMaxRows: 16, tableMaxCols: 10, maxChars: 5000 });
console.log(savedCheck.ndjson);
console.log(`SAVED ${outputPath}`);
