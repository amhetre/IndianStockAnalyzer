"""
Learning-centre content shown inside every generated report.

The content is plain data (list of section dicts made of typed blocks) so the
same text can be rendered into the Excel workbook and the HTML dashboard:

    {"id": ..., "title": ..., "blocks": [
        {"t": "h3",   "text": ...},
        {"t": "p",    "text": ...},
        {"t": "ul",   "items": [...]},
        {"t": "ol",   "items": [...]},
        {"t": "table","head": [...], "rows": [[...], ...]},
        {"t": "formula", "text": "Market Cap = CMP × Outstanding shares",
                         "note": "Example: ₹500 × 10 crore = ₹5,000 crore"},
        {"t": "note", "text": ...},
        {"t": "links","items": [(label, url, description), ...]},
    ]}

Everything here is general financial education. It is not investment advice.
"""
from __future__ import annotations

SECTIONS: list[dict] = [
    # ------------------------------------------------------------------ 1
    {
        "id": "basics",
        "title": "1. Stock market basics",
        "blocks": [
            {"t": "h3", "text": "1.1 What is a stock?"},
            {"t": "p", "text": "A stock (share / equity) represents ownership in a company. "
                              "If a company has 10 lakh total shares and you buy 1,000 shares, you own 0.1% "
                              "of it. If the company grows and becomes more profitable, your ownership can "
                              "become more valuable."},
            {"t": "table", "head": ["If the company has", "You purchase", "Your ownership"],
             "rows": [["Total shares: 10 lakh", "1,000 shares", "0.1%"]]},
            {"t": "p", "text": "You can potentially earn money through:"},
            {"t": "ol", "items": [
                "Capital appreciation – the share price increases.",
                "Dividends – the company distributes a portion of its profits to shareholders.",
                "Bonus shares – additional shares issued to existing shareholders.",
                "Stock splits – existing shares are divided into smaller face-value shares.",
            ]},
            {"t": "note", "text": "A good company does not automatically mean a good investment. "
                                  "You must also consider the price at which you purchase it."},

            {"t": "h3", "text": "1.2 Primary vs secondary market"},
            {"t": "table",
             "head": ["Primary market", "Secondary market"],
             "rows": [["Company issues shares", "Investors trade existing shares"],
                      ["IPO, FPO", "NSE, BSE"],
                      ["Money generally goes to the issuing company",
                       "Money goes to the selling investor"]]},

            {"t": "h3", "text": "1.3 Types of stocks"},
            {"t": "table", "head": ["Type", "Meaning"],
             "rows": [
                 ["Large-cap", "Established, relatively large companies"],
                 ["Mid-cap", "Medium-sized companies"],
                 ["Small-cap", "Smaller listed companies"],
                 ["Growth stocks", "Companies expected to grow rapidly"],
                 ["Value stocks", "Shares trading below estimated intrinsic value"],
                 ["Dividend stocks", "Companies with regular dividend distributions"],
                 ["Cyclical stocks", "Businesses affected by economic cycles"],
                 ["Defensive stocks", "Businesses with relatively stable demand"],
                 ["Multibagger stocks", "Shares that multiply in value over time"],
             ]},

            {"t": "h3", "text": "1.4 Important market terms"},
            {"t": "ul", "items": [
                "CMP: Current Market Price – the price at which the share last traded.",
                "Market Capitalisation: total market value of outstanding shares.",
                "52-week high / low: highest and lowest trading price in the last 52 weeks.",
                "Face Value: nominal value assigned to a share (used for splits/bonus).",
                "Book Value: accounting net worth attributable to shareholders.",
                "Volume: number of shares traded.",
                "Free Float: shares available for public trading (excludes promoter holdings).",
                "Liquidity: how easily shares can be bought or sold.",
                "Volatility: how much the share price fluctuates.",
            ]},
            {"t": "formula", "text": "Market Cap = CMP × Total Outstanding Shares",
             "note": "Example: CMP ₹500 × 10 crore shares = ₹5,000 crore market cap."},
        ],
    },
    # ------------------------------------------------------------------ 2
    {
        "id": "statements",
        "title": "2. The three financial statements",
        "blocks": [
            {"t": "p", "text": "Every listed company publishes three financial statements. Read all three "
                              "together – never judge a company using only its profit."},
            {"t": "table", "head": ["Statement", "What it tells you"],
             "rows": [
                 ["Balance Sheet", "What the company owns and owes (a snapshot)"],
                 ["Profit & Loss (P&L)", "How much it earns and spends over a period"],
                 ["Cash Flow Statement", "Where cash comes from and goes"],
             ]},

            {"t": "h3", "text": "2.1 Profit and Loss statement (P&L)"},
            {"t": "table", "head": ["Particulars", "Amount"],
             "rows": [
                 ["Revenue", "₹1,000 Cr"], ["Raw material expenses", "₹400 Cr"],
                 ["Employee expenses", "₹100 Cr"], ["Other operating expenses", "₹200 Cr"],
                 ["EBITDA", "₹300 Cr"], ["Depreciation", "₹50 Cr"], ["EBIT", "₹250 Cr"],
                 ["Interest expenses", "₹30 Cr"], ["PBT", "₹220 Cr"], ["Tax", "₹55 Cr"],
                 ["Net Profit (PAT)", "₹165 Cr"],
             ]},
            {"t": "ul", "items": [
                "Revenue: total income from selling products or services.",
                "Operating expenses: expenses required to operate the business.",
                "EBITDA: earnings before interest, taxes, depreciation and amortisation.",
                "Depreciation: reduction in the accounting value of physical assets over time.",
                "EBIT: earnings before interest and taxes.",
                "Interest: cost of borrowing money.",
                "PBT: profit before tax.",
                "PAT: profit after tax – the final accounting profit after taxes.",
            ]},
            {"t": "formula", "text": "EBITDA = Revenue − Operating Expenses"},
            {"t": "formula", "text": "EBIT = EBITDA − Depreciation"},
            {"t": "table", "head": ["Profit margin", "Formula", "Example"],
             "rows": [
                 ["Gross Profit Margin", "Gross Profit / Revenue × 100", "—"],
                 ["EBITDA Margin", "EBITDA / Revenue × 100", "300/1,000 = 30%"],
                 ["EBIT Margin", "EBIT / Revenue × 100", "250/1,000 = 25%"],
                 ["Net Profit Margin", "PAT / Revenue × 100", "165/1,000 = 16.5%"],
             ]},
            {"t": "note", "text": "The company retains ₹16.50 as net profit for every ₹100 of revenue. "
                                  "Higher margins are not always better – compare within the same industry "
                                  "and examine historical trends."},

            {"t": "h3", "text": "2.2 Balance sheet"},
            {"t": "formula", "text": "Assets = Liabilities + Shareholders' Equity"},
            {"t": "table", "head": ["Assets", "Amount"],
             "rows": [["Cash and bank balance", "₹100 Cr"], ["Inventory", "₹150 Cr"],
                      ["Receivables", "₹100 Cr"], ["Property and equipment", "₹400 Cr"],
                      ["Other assets", "₹250 Cr"], ["Total Assets", "₹1,000 Cr"]]},
            {"t": "table", "head": ["Liabilities and equity", "Amount"],
             "rows": [["Short-term borrowings", "₹100 Cr"], ["Long-term borrowings", "₹200 Cr"],
                      ["Trade payables", "₹100 Cr"], ["Other liabilities", "₹100 Cr"],
                      ["Shareholders' equity", "₹500 Cr"], ["Total", "₹1,000 Cr"]]},
            {"t": "p", "text": "What to examine: total assets, total liabilities, shareholders' equity, "
                              "cash & equivalents, borrowings, trade receivables, inventory, "
                              "reserves and surplus."},
            {"t": "p", "text": "Warning signs:"},
            {"t": "ul", "items": [
                "Debt growing faster than revenue.",
                "Receivables increasing much faster than sales.",
                "Inventory increasing without corresponding sales growth.",
                "Negative net worth.",
                "Significant contingent liabilities.",
                "Large unexplained changes in other assets.",
            ]},

            {"t": "h3", "text": "2.3 Cash flow statement"},
            {"t": "table", "head": ["Type", "Explanation"],
             "rows": [
                 ["CFO", "Cash Flow from Operations – cash generated by normal business operations"],
                 ["CFI", "Cash Flow from Investing – machinery bought, assets sold, investments"],
                 ["CFF", "Cash Flow from Financing – borrowing, repayment, dividends, share issuance"],
             ]},
            {"t": "table", "head": ["Particulars", "Amount"],
             "rows": [["Net Profit", "₹100 Cr"], ["Operating Cash Flow", "₹130 Cr"],
                      ["Capital Expenditure", "₹40 Cr"], ["Free Cash Flow", "₹90 Cr"]]},
            {"t": "formula", "text": "Free Cash Flow (FCF) = CFO − Capital Expenditure",
             "note": "FCF = 130 − 40 = ₹90 Cr. Cash is needed to repay debt, pay dividends, expand, "
                     "acquire and invest in future growth."},
            {"t": "note", "text": "A company reporting ₹100 crore profit but consistently generating "
                                  "negative operating cash flow needs further investigation. Negative FCF "
                                  "is not automatically bad – a growing company may invest heavily in "
                                  "factories, technology or infrastructure."},
        ],
    },
    # ------------------------------------------------------------------ 3
    {
        "id": "ratios",
        "title": "3. Important financial ratios",
        "blocks": [
            {"t": "h3", "text": "3.1 Profitability ratios"},
            {"t": "table", "head": ["Ratio", "Formula", "What it tells you"],
             "rows": [
                 ["ROE", "PAT / Average Equity × 100", "Return generated on shareholders' funds"],
                 ["ROCE", "EBIT / Average Capital Employed × 100", "Efficiency of total capital"],
                 ["ROA", "PAT / Average Total Assets × 100", "Profitability of assets"],
                 ["EBITDA Margin", "EBITDA / Revenue × 100", "Operating profitability"],
                 ["Net Profit Margin", "PAT / Revenue × 100", "Final profitability"],
             ]},
            {"t": "formula", "text": "ROE = Net profit / Average shareholders' equity × 100",
             "note": "PAT ₹100 Cr ÷ average equity ₹500 Cr = 20%. The company earns ₹20 of profit each "
                     "year for every ₹100 of shareholders' money."},
            {"t": "formula", "text": "ROCE = EBIT / Average capital employed × 100",
             "note": "EBIT ₹200 Cr ÷ capital employed ₹1,000 Cr = 20%. Look for a consistent, improving "
                     "ROCE that is higher than the company's cost of capital and better than peers."},
            {"t": "note", "text": "For many non-financial businesses a sustained ROCE above 15–20% is "
                                  "attractive, but there is no universal threshold. A high ROE driven by "
                                  "excessive debt or unusually low equity is not quality."},

            {"t": "h3", "text": "3.2 Valuation ratios"},
            {"t": "formula", "text": "P/E = CMP / EPS", "note": "CMP ₹500 ÷ EPS ₹25 = 20 → you pay ₹20 "
                                                                "for every ₹1 of annual earnings."},
            {"t": "formula", "text": "P/B = CMP / Book Value Per Share",
             "note": "CMP ₹400 ÷ book value ₹200 = 2. The market values equity at twice its accounting "
                     "book value. Especially useful for banks; read with ROE."},
            {"t": "formula", "text": "PEG = P/E ÷ Expected EPS Growth Rate",
             "note": "P/E 30 ÷ growth 20% = 1.5. Lower can be more attractive, but growth estimates "
                     "can be wrong."},
            {"t": "formula", "text": "EV/EBITDA = Enterprise Value / EBITDA",
             "note": "Enterprise Value = Market Cap + Total Debt − Cash. Useful when comparing companies "
                     "with different debt levels."},
            {"t": "formula", "text": "P/S = Market Cap / Annual Revenue",
             "note": "Useful for low- or negative-earnings companies, but revenue alone does not tell "
                     "you whether the business is profitable."},
            {"t": "formula", "text": "Dividend Yield = Annual Dividend Per Share / CMP × 100",
             "note": "₹10 dividend on a ₹200 share = 5%. A very high yield may mean the price has fallen "
                     "because the business is deteriorating."},
            {"t": "formula", "text": "Earnings Yield = EPS / CMP × 100",
             "note": "The inverse of the P/E ratio."},
            {"t": "formula", "text": "P/FCF = Market Capitalisation / Free Cash Flow",
             "note": "Not meaningful when free cash flow is negative."},
            {"t": "note", "text": "Never conclude that a 10 P/E stock is automatically cheaper than a "
                                  "30 P/E stock – compare growth, profitability, risk and industry peers."},

            {"t": "h3", "text": "3.3 Debt and financial safety ratios"},
            {"t": "formula", "text": "Debt-to-Equity = Total Debt / Shareholders' Equity",
             "note": "Debt ₹300 Cr ÷ equity ₹500 Cr = 0.60 → ₹0.60 of debt for every ₹1 of equity."},
            {"t": "formula", "text": "Interest Coverage = EBIT / Interest Expense",
             "note": "EBIT ₹200 Cr ÷ interest ₹40 Cr = 5 times."},
            {"t": "table", "head": ["Interest coverage", "General interpretation"],
             "rows": [["Below 1", "Serious warning – profit does not cover interest"],
                      ["1–2", "Weak coverage"], ["2–3", "Needs attention"],
                      ["3–5", "Reasonable"], ["Above 5", "Generally comfortable"]]},
            {"t": "formula", "text": "Current Ratio = Current Assets / Current Liabilities",
             "note": "₹400 Cr current assets ÷ ₹200 Cr current liabilities = 2.0."},
            {"t": "formula", "text": "Quick Ratio = (Current Assets − Inventory − Prepaid Expenses) "
                                     "/ Current Liabilities",
             "note": "Measures short-term liquidity without relying on selling inventory."},
            {"t": "formula", "text": "Net Debt = Total Debt − Cash and Cash Equivalents",
             "note": "Debt ₹500 Cr − cash ₹200 Cr = net debt ₹300 Cr."},
            {"t": "formula", "text": "Net Debt / EBITDA = Net Debt / EBITDA",
             "note": "High ratio = greater financial risk. Interpret carefully for banks and volatile "
                     "earnings."},

            {"t": "h3", "text": "3.4 Growth ratios"},
            {"t": "table", "head": ["Metric", "What it measures"],
             "rows": [["Revenue Growth", "Sales growth"], ["EBITDA Growth", "Operating earnings growth"],
                      ["EBIT Growth", "Operating profit growth"], ["PAT Growth", "Net profit growth"],
                      ["EPS Growth", "Earnings growth per share"], ["FCF Growth", "Free cash flow growth"]]},
            {"t": "formula", "text": "CAGR = (Ending Value / Beginning Value)^(1/n) − 1",
             "note": "Revenue ₹100 Cr → ₹200 Cr in 5 years: (200/100)^(1/5) − 1 = 14.87% a year, "
                     "compounded."},
            {"t": "note", "text": "Always analyse revenue CAGR and profit CAGR together. 20% revenue "
                                  "growth with only 5% profit growth may mean rising costs or "
                                  "deteriorating margins."},

            {"t": "h3", "text": "3.5 Efficiency ratios"},
            {"t": "table", "head": ["Ratio", "Formula"],
             "rows": [
                 ["Asset Turnover", "Revenue / Average Total Assets"],
                 ["Inventory Turnover", "COGS / Average Inventory"],
                 ["Receivables Turnover", "Credit Sales / Average Receivables"],
                 ["Payables Turnover", "Purchases / Average Payables"],
             ]},
            {"t": "formula", "text": "Cash Conversion Cycle (CCC) = DIO + DSO − DPO",
             "note": "DIO = days inventory outstanding, DSO = days sales outstanding, DPO = days payables "
                     "outstanding. A lower CCC can indicate better working-capital efficiency "
                     "(industry differences matter)."},
        ],
    },
    # ------------------------------------------------------------------ 4-6
    {
        "id": "ownership",
        "title": "4-6. Shareholding, management and business quality",
        "blocks": [
            {"t": "h3", "text": "4.1 Promoter holding"},
            {"t": "p", "text": "Financial statements tell you about the business; shareholding patterns "
                              "tell you who owns it – especially important for Indian stocks. Promoters "
                              "are the individuals or entities that establish or control the company."},
            {"t": "ul", "items": [
                "Current promoter holding and the trend over the last 3 years.",
                "Whether promoters are increasing or decreasing their stake.",
                "Pledged promoter shares.",
                "Reasons for any change in ownership.",
            ]},
            {"t": "table", "head": ["Quarter", "Promoter holding"],
             "rows": [["Q1", "55%"], ["Q2", "55%"], ["Q3", "54.5%"], ["Q4", "54%"], ["Q5", "52%"]]},
            {"t": "note", "text": "A declining pattern requires investigation – but promoter holding can "
                                  "legitimately fall because of an OFS, a new share issue or a regulatory "
                                  "requirement."},

            {"t": "h3", "text": "4.2 Promoter pledge"},
            {"t": "p", "text": "Pledging means promoters use their shares as collateral to secure "
                              "borrowing. If the share price falls sharply, lenders may demand extra "
                              "collateral or sell the pledged shares – which pushes the price down "
                              "further."},
            {"t": "ul", "items": [
                "Percentage of promoter holding pledged.",
                "Change in pledged shares and whether the pledge is increasing.",
                "Reason for pledging.",
            ]},
            {"t": "note", "text": "A high or rapidly increasing pledge is a warning sign."},

            {"t": "h3", "text": "4.3 Institutional shareholding"},
            {"t": "table", "head": ["Shareholder category", "Example holding"],
             "rows": [["Promoters", "55%"], ["FII/FPI (foreign portfolio investors)", "15%"],
                      ["DII (domestic institutions: mutual funds, insurance)", "20%"],
                      ["Retail and others", "10%"]]},
            {"t": "note", "text": "Institutional buying is useful information, but it is not proof that "
                                  "a stock is a good investment."},

            {"t": "h3", "text": "4.4 Share dilution"},
            {"t": "p", "text": "If a company with 10 crore shares issues 2 crore more, your ownership "
                              "percentage falls unless you participate. Check outstanding shares, ESOP "
                              "issuance, preferential allotments, QIPs and convertible securities."},

            {"t": "h3", "text": "5. Management and corporate governance"},
            {"t": "p", "text": "A financially strong company can still become a poor investment if "
                              "management makes bad decisions. Check:"},
            {"t": "ol", "items": [
                "Promoter background and management experience.",
                "Corporate governance history.",
                "Related-party transactions (transparent and commercially reasonable?).",
                "Auditor qualifications, resignations and changes.",
                "Contingent liabilities (lawsuits, guarantees).",
                "Regulatory investigations.",
                "Capital allocation decisions.",
                "Management guidance versus actual performance.",
            ]},
            {"t": "note", "text": "A company with excellent financial ratios but questionable "
                                  "governance deserves a significant risk premium."},

            {"t": "h3", "text": "6. Understanding business quality"},
            {"t": "p", "text": "Before buying a stock, understand what the company actually does: what "
                              "it sells, who its customers are, how it earns revenue, its major costs, "
                              "its competitors, its pricing power, whether demand is rising, and whether "
                              "it has a sustainable competitive advantage."},
            {"t": "table", "head": ["Economic moat", "Explanation"],
             "rows": [
                 ["Brand", "Customers trust the brand"],
                 ["Network effect", "More users make the service more valuable"],
                 ["Cost advantage", "The company produces at a lower cost"],
                 ["Switching cost", "Customers find it difficult to change providers"],
                 ["Distribution", "Strong distribution network"],
                 ["Technology", "Proprietary technology or expertise"],
                 ["Regulatory barrier", "Difficult entry requirements"],
             ]},
            {"t": "p", "text": "Compare a company with its competitors on revenue growth, profit growth, "
                              "ROE, ROCE, margins, debt, P/E, P/B, cash flow and market share. "
                              "Never compare a bank's ratios directly with a manufacturing company's."},
        ],
    },
    # ------------------------------------------------------------------ 7-8
    {
        "id": "valuation",
        "title": "7-8. Price, valuation and result analysis",
        "blocks": [
            {"t": "p", "text": "A company's business performance and its share price are two different "
                              "things: profit can grow 20% while the price falls because investors "
                              "expected 30%; weak results can still push a price up if they beat "
                              "expectations."},
            {"t": "h3", "text": "7.1 Intrinsic value (DCF)"},
            {"t": "formula", "text": "Intrinsic Value = Σ FCF(t) / (1+r)^t + Terminal Value / (1+r)^n",
             "note": "FCF = future free cash flow, r = discount rate, n = forecast period. Small changes "
                     "in growth or discount-rate assumptions can produce very different valuations."},
            {"t": "h3", "text": "7.2 Margin of safety"},
            {"t": "formula", "text": "MOS = (Intrinsic Value − Current Price) / Intrinsic Value × 100",
             "note": "Intrinsic value ₹500, market price ₹350 → MOS = 30%. You are buying at a 30% "
                     "discount to your estimate, which protects against errors in your assumptions."},
            {"t": "h3", "text": "7.3 Relative valuation"},
            {"t": "ul", "items": [
                "Compare with the stock's own historical valuation.",
                "Compare with competitors and the industry average.",
                "Compare with historical and expected future growth.",
            ]},
            {"t": "table", "head": ["Company", "P/E"],
             "rows": [["Company A", "15"], ["Company B", "25"], ["Company C", "35"]]},
            {"t": "note", "text": "You cannot automatically conclude Company A is the best investment – "
                                  "it may have declining profits while Company C has strong growth and "
                                  "better business quality."},
            {"t": "h3", "text": "7.4 Why is a stock price falling?"},
            {"t": "ul", "items": [
                "Revenue decline or lower profitability.", "Increasing debt or poor quarterly results.",
                "Management issues or promoter selling.", "High valuation correction.",
                "Industry slowdown or regulatory issues.",
                "Market-wide correction or declining growth expectations.",
            ]},
            {"t": "note", "text": "When a stock falls 30%, investigate the reason before considering it "
                                  "a buying opportunity."},
            {"t": "h3", "text": "7.5 Why is a stock expensive?"},
            {"t": "ul", "items": [
                "Strong future growth expectations, high ROCE/ROE, excellent management.",
                "Strong competitive advantage, low debt, high institutional demand.",
                "Market speculation or outright overvaluation.",
            ]},
            {"t": "p", "text": "Your job is to distinguish a high-quality expensive stock from an "
                              "overvalued stock with unrealistic expectations."},

            {"t": "h3", "text": "8.1 Quarterly analysis (YoY and QoQ)"},
            {"t": "table", "head": ["Metric", "Q2 FY26", "Q2 FY27", "Growth"],
             "rows": [["Revenue", "₹1,000 Cr", "₹1,200 Cr", "20%"],
                      ["EBITDA", "₹200 Cr", "₹240 Cr", "20%"],
                      ["PAT", "₹100 Cr", "₹130 Cr", "30%"],
                      ["Debt", "₹500 Cr", "₹700 Cr", "40%"]]},
            {"t": "ul", "items": [
                "YoY: the same quarter compared with the same quarter a year earlier (avoids seasonality).",
                "QoQ: one quarter compared with the immediately preceding quarter.",
            ]},
            {"t": "note", "text": "In the example above revenue and EBITDA growth are healthy and profit "
                                  "growth is stronger – but debt growth of 40% is concerning and needs "
                                  "investigation."},

            {"t": "h3", "text": "8.2 Annual analysis"},
            {"t": "p", "text": "Analyse at least five years of revenue, EBITDA, EBIT, PAT, EPS, CFO, FCF, "
                              "debt, ROE, ROCE and share count. Look for consistency, not one good year."},
            {"t": "h3", "text": "8.3 Earnings quality"},
            {"t": "table", "head": ["Situation", "Interpretation"],
             "rows": [
                 ["PAT increasing, CFO increasing", "Generally positive"],
                 ["PAT increasing, CFO decreasing", "Investigate earnings quality"],
                 ["Revenue increasing, receivables rising rapidly", "Possible collection problem"],
                 ["EBITDA increasing, margins falling", "Growth may be cost-driven"],
                 ["EPS increasing, shares declining", "Buybacks may contribute"],
                 ["PAT increasing, debt increasing rapidly", "Examine funding and cash generation"],
             ]},
        ],
    },
    # ------------------------------------------------------------------ 9-11
    {
        "id": "industry",
        "title": "9-11. Industry ratios, corporate actions, analysis types",
        "blocks": [
            {"t": "h3", "text": "9. Special ratios for different industries"},
            {"t": "p", "text": "One of the biggest mistakes beginners make is applying the same ratios "
                              "to every company."},
            {"t": "table", "head": ["Industry", "Important metrics"],
             "rows": [
                 ["Banking", "NIM, GNPA, NNPA, CASA, ROA, ROE, Capital Adequacy"],
                 ["NBFC", "GNPA, NNPA, AUM growth, NIM, credit cost, Capital Adequacy"],
                 ["Insurance", "Embedded value, VNB margin, solvency ratio"],
                 ["IT Services", "Revenue growth, EBIT margin, attrition, utilisation"],
                 ["Automobile", "Volume growth, ASP, EBITDA margin, market share"],
                 ["FMCG", "Volume growth, pricing growth, gross margin"],
                 ["Manufacturing", "ROCE, capacity utilisation, EBITDA margin"],
                 ["Infrastructure", "Order book, debt, project execution, cash flow"],
                 ["Real Estate", "Pre-sales, collections, inventory, net debt"],
                 ["Telecom", "ARPU, subscriber growth, churn"],
                 ["Pharma", "R&D spending, product pipeline, regulatory compliance"],
                 ["Metals", "Realisations, production, cost per tonne, net debt"],
             ]},
            {"t": "formula", "text": "NIM = Net Interest Income / Average Earning Assets × 100",
             "note": "GNPA = gross non-performing assets; NNPA = net NPAs after provisions; "
                     "CASA = current & savings deposits / total deposits; credit cost = loan-loss "
                     "provisions / loan book. For banks, conventional D/E and interest coverage are "
                     "not interpreted like manufacturers."},
            {"t": "h3", "text": "10. Corporate actions"},
            {"t": "table", "head": ["Corporate action", "Meaning"],
             "rows": [
                 ["Dividend", "Distribution of profits to shareholders"],
                 ["Interim dividend", "Declared during the financial year"],
                 ["Final dividend", "Recommended after the financial year-end"],
                 ["Bonus issue", "Additional shares issued to existing shareholders"],
                 ["Stock split", "Face value divided into smaller units"],
                 ["Rights issue", "Existing shareholders offered new shares"],
                 ["Buyback", "The company purchases its own shares"],
                 ["OFS", "Existing shareholders sell their shares"],
                 ["Merger", "Two or more businesses combine"],
                 ["Demerger", "A business is separated into independent entities"],
             ]},
            {"t": "note", "text": "A bonus issue or stock split does not automatically increase your "
                                  "total investment value – the share price adjusts accordingly."},
            {"t": "h3", "text": "11. Fundamental vs technical analysis"},
            {"t": "table", "head": ["Fundamental analysis", "Technical analysis"],
             "rows": [
                 ["Examines business quality", "Examines price movement"],
                 ["Studies financial statements", "Studies charts"],
                 ["Analyses valuation", "Analyses trends"],
                 ["Examines management", "Examines trading volume"],
                 ["Answers: what company to invest in",
                  "Answers: at what price to buy or sell (entry/exit timing)"],
             ]},
            {"t": "note", "text": "You can use both, but don't confuse a chart pattern with evidence of "
                                  "business quality."},
        ],
    },
    # ------------------------------------------------------------------ 12-14
    {
        "id": "risks",
        "title": "12-14. Risks, period analysis and stock selection",
        "blocks": [
            {"t": "h3", "text": "12. Major risks you must identify"},
            {"t": "table", "head": ["Risk", "Explanation"],
             "rows": [
                 ["Business risk", "Business model becomes less profitable"],
                 ["Financial risk", "Excessive borrowing"],
                 ["Liquidity risk", "Difficulty meeting obligations"],
                 ["Valuation risk", "Paying too much"],
                 ["Governance risk", "Management misconduct"],
                 ["Regulatory risk", "Changes in laws and regulations"],
                 ["Competition risk", "Competitors reduce market share"],
                 ["Technology risk", "Technology makes the business obsolete"],
                 ["Concentration risk", "Dependence on a few customers/products"],
                 ["Commodity risk", "Raw material price fluctuations"],
                 ["Currency risk", "Foreign exchange fluctuations"],
             ]},
            {"t": "p", "text": "Common financial red flags:"},
            {"t": "ul", "items": [
                "Persistent negative operating cash flow.",
                "High promoter pledge or frequent equity dilution.",
                "Repeated auditor resignations or unexplained related-party transactions.",
                "Debt growing faster than operating earnings.",
                "High receivables relative to sales or large contingent liabilities.",
                "Profit increasing without cash generation.",
                "Sudden changes in accounting policies or frequent guidance misses.",
            ]},
            {"t": "note", "text": "One warning sign does not necessarily mean avoid the company. "
                                  "Multiple unexplained warning signs deserve serious investigation."},

            {"t": "h3", "text": "13. Analysing performance over different periods"},
            {"t": "table", "head": ["Period", "What to investigate"],
             "rows": [
                 ["3 months", "Latest price movement and recent developments"],
                 ["6 months", "Short-term performance and valuation change"],
                 ["9 months", "Medium-term trend"],
                 ["1 year", "Annual stock and business performance"],
                 ["3 years", "Business consistency and growth"],
                 ["5 years", "Long-term business quality and wealth creation"],
             ]},
            {"t": "p", "text": "For each period calculate: price return, revenue growth, EBITDA growth, "
                              "PAT growth, EPS growth, debt change, ROE, ROCE, cash-flow trend and "
                              "valuation trend."},
            {"t": "note", "text": "Price CAGR and financial CAGR are different. A stock can deliver 30% "
                                  "price CAGR while earnings grow only 10% – the market has assigned a "
                                  "higher valuation multiple. Earnings can also grow while the price "
                                  "stays flat if multiples contract."},

            {"t": "h3", "text": "14. How to identify a fundamentally strong stock"},
            {"t": "table",
             "head": ["Category", "What to examine", "Suggested importance"],
             "rows": [
                 ["Business quality", "Business model, moat, competition", "15%"],
                 ["Revenue and profit growth", "3Y and 5Y CAGR", "15%"],
                 ["Profitability", "ROE, ROCE, margins", "15%"],
                 ["Financial health", "Debt, interest coverage, liquidity", "15%"],
                 ["Cash flow", "CFO, FCF, cash conversion", "10%"],
                 ["Valuation", "P/E, P/B, EV/EBITDA, DCF", "15%"],
                 ["Management", "Promoter holding, pledge, governance", "10%"],
                 ["Industry outlook", "Growth opportunities and risks", "5%"],
                 ["Total", "", "100%"],
             ]},
            {"t": "table", "head": ["Score", "Classification"],
             "rows": [["85–100", "Excellent fundamentals"], ["70–84", "Strong fundamentals"],
                      ["55–69", "Average / needs investigation"], ["40–54", "Weak fundamentals"],
                      ["Below 40", "High-risk fundamentals"]]},
            {"t": "note", "text": "These weights are an illustrative screening framework, not a "
                                  "universal investment formula. Keep valuation as a separate decision: "
                                  "a fundamentally excellent company can still be a poor purchase if "
                                  "you pay too much."},
        ],
    },
    # ------------------------------------------------------------------ 15-16
    {
        "id": "checklist",
        "title": "15. Stock research checklist",
        "blocks": [
            {"t": "p", "text": "Tick every item before purchasing any share. Your progress is saved in "
                              "this browser session only."},
            {"t": "checklist", "items": [
                "I understand what the company sells, who its customers are and how it makes money.",
                "I have read the P&L, balance sheet and cash-flow statement together (not profit alone).",
                "Revenue and profit growth are consistent over 3 and 5 years (not one good year).",
                "ROE and ROCE are healthy and above the cost of capital, over several years.",
                "Debt is manageable and interest coverage is above 3x (or the sector norm).",
                "Operating cash flow supports reported profits (cash conversion ≥ 0.8).",
                "Promoter holding is stable or rising and the pledge level is low.",
                "No unexplained related-party transactions, auditor resignations or governance issues.",
                "Valuation is reasonable versus peers and its own history (P/E, PEG, EV/EBITDA).",
                "I know why the price recently rose or fell – and it is not just market noise.",
                "I have checked the industry-specific metrics that matter for this sector.",
                "I have listed the key risks (business, financial, governance, regulatory, valuation).",
                "I have a written thesis, a target buy price and a margin of safety.",
                "I am not relying on tips, social media or stock recommendations alone.",
                "My position size fits my risk appetite and portfolio.",
            ]},

            {"t": "h3", "text": "16. Where to get financial data for Indian stocks"},
            {"t": "p", "text": "Use reliable sources instead of relying only on social media, YouTube "
                              "or stock tips."},
            {"t": "links", "items": [
                ("Screener.in", "https://www.screener.in",
                 "Financial statements, ratios, quarterly results, shareholding patterns and peer "
                 "comparison."),
                ("NSE India", "https://www.nseindia.com",
                 "Official corporate announcements, financial results, shareholding disclosures and "
                 "exchange information."),
                ("BSE India", "https://www.bseindia.com",
                 "Corporate filings, announcements, results and annual reports."),
            ]},
            {"t": "note", "text": "This report is generated automatically from public data for "
                                  "education. It is not investment advice."},
        ],
    },
]


def sections_for_excel() -> list[list[dict]]:
    """Split the sections into four balanced groups so no Excel sheet gets too long."""
    groups: dict[str, list[dict]] = {
        "learn1": [], "learn2": [], "learn3": [], "learn4": [],
    }
    plan = {"basics": "learn1",
            "statements": "learn2", "ratios": "learn2",
            "ownership": "learn3", "valuation": "learn3",
            "industry": "learn4", "risks": "learn4", "checklist": "learn4"}
    for s in SECTIONS:
        groups[plan[s["id"]]].append(s)
    return [groups["learn1"], groups["learn2"], groups["learn3"], groups["learn4"]]


EXCEL_SHEET_TITLES = ["Learn 1 - Stock Basics", "Learn 2 - Fin statements",
                      "Learn 3 - Ratios & valuation", "Learn 4 - Risk & checklist"]
