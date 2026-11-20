// npm install docxtemplater pizzip   (optional; check the project's current licence and modules: verifieer actuele regel)
// Needs templates/kpi-template.docx with {administratie}, {omzet}, {kosten}, {resultaat} (create it with make_docx_template.py).
const PizZip = require("pizzip");
const Docxtemplater = require("docxtemplater");
const fs = require("fs");
const zip = new PizZip(fs.readFileSync(__dirname + "/kpi-template.docx", "binary"));
const doc = new Docxtemplater(zip, { paragraphLoop: true, linebreaks: true });
doc.render(JSON.parse(fs.readFileSync(__dirname + "/docxtemplater-data.json", "utf8")));
fs.writeFileSync(__dirname + "/kpi-report.docx", doc.getZip().generate({ type: "nodebuffer" }));
