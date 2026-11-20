#set document(title: "Key figures [Voorbeeld] BV")
= Key figures [Voorbeeld] BV
#let rows = csv("../data/yuki-kpis.csv").slice(1)
#table(columns: 3, [*KPI*], [*Value*], [*Unit*], ..rows.map(r => (r.at(4), r.at(5), r.at(6))).flatten())
_EXAMPLE with made-up [Voorbeeld] data. Not tax advice._
