'use client';

/**
 * SalesProfitPDFDoc
 * -----------------
 * @react-pdf/renderer document for the Sales & Profit dashboard.
 *
 * Renders a PROPER PDF report — actual selectable text from real data,
 * not a DOM screenshot. Pages:
 *   Page 1 – Executive summary: KPIs + Financial Summary + Channel breakdown
 *   Page 2 – Revenue trend by year table + Store ranking table
 */

import React from 'react';
import {
  Document, Font, Page, StyleSheet, Text, View, pdf,
} from '@react-pdf/renderer';

// ── Load Unicode-capable font for Vietnamese (served from /public/fonts) ────────
const _FONT_ORIGIN =
  typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000';

Font.register({
  family: 'NotoSans',
  fonts: [
    { src: `${_FONT_ORIGIN}/fonts/NotoSans-Regular.ttf`, fontWeight: 'normal' },
    { src: `${_FONT_ORIGIN}/fonts/NotoSans-Bold.ttf`, fontWeight: 'bold' },
  ],
});

// Fallback to Helvetica when font can't be fetched (offline mode).
const FONT = 'NotoSans';
const FONT_B = 'NotoSans';

// ── Types ─────────────────────────────────────────────────────────────────────
export interface SalesDashRes {
  ytd: number; mtd: number; total: number;
  ytd_profit: number; mtd_profit: number; total_profit: number;
  avg_profit_margin: number; yoy_growth: number; mom_growth: number;
  trend: { labels: string[]; data: number[] };
  profit_trend: { labels: string[]; data: number[] };
  store_pie: { labels: string[]; data: number[] };
  last_updated: string | null;
}
export interface SalesChRes {
  channels: { channel: string; revenue: number; profit: number; transactions: number; share_pct: number }[];
  total_revenue: number;
}
export interface SalesTrendRow { date: string; sales: number; profit: number; }
export interface SalesPieRow   { name: string; value: number; }

export interface SalesProfitPDFDocProps {
  data: SalesDashRes;
  chData?: SalesChRes | null;
  trendRows: SalesTrendRow[];
  pieRows: SalesPieRow[];
  filterLabel: string;
  username?: string;
  role?: string;
}

// ── Formatters ────────────────────────────────────────────────────────────────
const fmtM = (v: number) => {
  const n = v ?? 0;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3)  return `$${(n / 1e3).toFixed(1)}K`;
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);
};
const fmtPct    = (v: number) => `${((v ?? 0) * 100).toFixed(1)}%`;
const fmtGrowth = (v: number) => `${(v ?? 0) >= 0 ? '+' : ''}${(v ?? 0).toFixed(1)}%`;

// ── Color palette ─────────────────────────────────────────────────────────────
const C = {
  navyBg:   '#1e3a5f',
  navyText: '#ffffff',
  navySub:  '#93c5fd',
  navyBdr:  '#3b82f6',
  accent:   '#2563eb',
  slate9:   '#0f172a',
  slate7:   '#334155',
  slate5:   '#64748b',
  slate3:   '#cbd5e1',
  slate2:   '#e2e8f0',
  slate1:   '#f1f5f9',
  white:    '#ffffff',
  green:    '#15803d',
  red:      '#b91c1c',
  amber:    '#b45309',
};

// ── StyleSheet ────────────────────────────────────────────────────────────────
const S = StyleSheet.create({
  page: { fontFamily: FONT, paddingBottom: 44, backgroundColor: '#f8fafc' },

  // ── Cover header
  cHeader:   { backgroundColor: C.navyBg, padding: '28 36 20 36', marginBottom: 24 },
  cTitle:    { fontSize: 20, fontFamily: FONT_B, fontWeight: 'bold', color: C.navyText, marginBottom: 4 },
  cSub:      { fontSize: 10, color: C.navySub, marginBottom: 14 },
  cMetaRow:  { flexDirection: 'row', justifyContent: 'space-between', borderTopWidth: 1, borderTopColor: C.navyBdr, paddingTop: 8 },
  cMeta:     { fontSize: 8, color: '#cbd5e1' },

  // ── Inner page header
  pHeader:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: C.navyBg, padding: '10 36', marginBottom: 18 },
  pHeaderTitle: { fontSize: 10, fontFamily: FONT_B, fontWeight: 'bold', color: C.navyText },
  pHeaderSub:   { fontSize: 8, color: C.navySub },

  // ── Body
  body: { paddingHorizontal: 36 },

  // ── Section
  sec:      { marginBottom: 16 },
  secTitle: { fontSize: 9, fontFamily: FONT_B, fontWeight: 'bold', color: C.navyText, backgroundColor: C.accent, padding: '5 10', marginBottom: 10, borderRadius: 2 },

  // ── KPI cards
  kpiRow:  { flexDirection: 'row', gap: 8, marginBottom: 8 },
  kpiCard: { flex: 1, backgroundColor: C.white, border: 1, borderColor: C.slate2, borderRadius: 4, padding: '8 10', borderTopWidth: 3, borderTopColor: C.accent },
  kpiLbl:  { fontSize: 7, color: C.slate5, marginBottom: 4 },
  kpiVal:  { fontSize: 13, fontFamily: FONT_B, fontWeight: 'bold', color: C.slate9 },
  kpiSub:  { fontSize: 7, color: C.slate5, marginTop: 2 },
  green:   { color: C.green },
  red:     { color: C.red },
  amber:   { color: C.amber },

  // ── Summary key-value box
  sBox: { backgroundColor: C.white, border: 1, borderColor: C.slate2, borderRadius: 4, padding: 12, marginBottom: 10 },
  sRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3, borderBottomWidth: 0.5, borderBottomColor: C.slate2 },
  sLbl: { fontSize: 8, color: C.slate5 },
  sVal: { fontSize: 8, fontFamily: FONT_B, fontWeight: 'bold', color: C.slate7 },

  // ── Table
  tbl:    { width: '100%', marginBottom: 4 },
  tHead:  { flexDirection: 'row', backgroundColor: '#1e40af', padding: '5 0', borderRadius: 2 },
  tHCell: { fontSize: 8, fontFamily: FONT_B, fontWeight: 'bold', color: C.white, paddingHorizontal: 8, flex: 1, textAlign: 'center' },
  tHCL:   { textAlign: 'left' },
  tRow:   { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: C.slate2, paddingVertical: 4 },
  tAlt:   { backgroundColor: C.slate1 },
  tCell:  { fontSize: 8, color: C.slate7, paddingHorizontal: 8, flex: 1, textAlign: 'center' },
  tCL:    { textAlign: 'left' },
  tBold:  { fontFamily: FONT_B, fontWeight: 'bold' },

  // ── Note
  note: { fontSize: 7, color: C.slate5, marginTop: 6 },

  // ── Footer
  footer:    { position: 'absolute', bottom: 14, left: 36, right: 36, flexDirection: 'row', justifyContent: 'space-between', borderTopWidth: 0.5, borderTopColor: C.slate3, paddingTop: 4 },
  footerTxt: { fontSize: 7, color: '#94a3b8' },
});

// ── Main document ─────────────────────────────────────────────────────────────
export function SalesProfitPDFDoc({
  data, chData, trendRows, pieRows, filterLabel, username, role,
}: SalesProfitPDFDocProps) {
  const generated = new Date().toLocaleString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });

  // Aggregate trend rows by year
  const yearMap = new Map<string, { sales: number; profit: number }>();
  trendRows.forEach(r => {
    const y = r.date.slice(0, 4);
    const cur = yearMap.get(y) ?? { sales: 0, profit: 0 };
    yearMap.set(y, { sales: cur.sales + r.sales, profit: cur.profit + r.profit });
  });
  const yearRows = Array.from(yearMap, ([year, v]) => ({
    year,
    sales: v.sales,
    profit: v.profit,
    margin: v.sales > 0 ? (v.profit / v.sales) * 100 : 0,
  })).sort((a, b) => a.year.localeCompare(b.year));

  // Margin color
  const marginColor = data.avg_profit_margin >= 0.2 ? C.green : data.avg_profit_margin >= 0.1 ? C.amber : C.red;
  const marginLabel = data.avg_profit_margin >= 0.2 ? 'Above Target' : data.avg_profit_margin >= 0.1 ? 'On Track' : 'Below Target';

  return (
    <Document
      title="Sales & Profit Report"
      author={username ?? 'BI Dashboard'}
      subject={`Period: ${filterLabel}`}
      creator="BI Dashboard System"
    >
      {/* ════════════════════════════════════════
          PAGE 1 – Executive Summary
          ════════════════════════════════════════ */}
      <Page size="A4" style={S.page}>
        {/* Cover header */}
        <View style={S.cHeader}>
          <Text style={S.cTitle}>Sales & Profit Report</Text>
          <Text style={S.cSub}>Business Intelligence Dashboard – Executive Summary</Text>
          <View style={S.cMetaRow}>
            <Text style={S.cMeta}>Period: {filterLabel}</Text>
            <Text style={S.cMeta}>Generated: {generated}</Text>
            {username && <Text style={S.cMeta}>User: {username}{role ? ` (${role})` : ''}</Text>}
          </View>
        </View>

        <View style={S.body}>
          {/* KPI Section */}
          <View style={S.sec}>
            <Text style={S.secTitle}>KEY PERFORMANCE INDICATORS</Text>

            {/* Row 1 */}
            <View style={S.kpiRow}>
              <View style={[S.kpiCard, { borderTopColor: '#2563eb' }]}>
                <Text style={S.kpiLbl}>YTD SALES</Text>
                <Text style={S.kpiVal}>{fmtM(data.ytd)}</Text>
                <Text style={S.kpiSub}>Year-to-date revenue</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: C.green }]}>
                <Text style={S.kpiLbl}>TOTAL PROFIT</Text>
                <Text style={S.kpiVal}>{fmtM(data.total_profit)}</Text>
                <Text style={S.kpiSub}>All-time gross profit</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: marginColor }]}>
                <Text style={S.kpiLbl}>PROFIT MARGIN</Text>
                <Text style={[S.kpiVal, { color: marginColor }]}>{fmtPct(data.avg_profit_margin)}</Text>
                <Text style={[S.kpiSub, { color: marginColor }]}>{marginLabel}</Text>
              </View>
            </View>

            {/* Row 2 */}
            <View style={S.kpiRow}>
              <View style={[S.kpiCard, { borderTopColor: data.yoy_growth >= 0 ? C.green : C.red }]}>
                <Text style={S.kpiLbl}>YoY GROWTH</Text>
                <Text style={[S.kpiVal, data.yoy_growth >= 0 ? S.green : S.red]}>
                  {fmtGrowth(data.yoy_growth)}
                </Text>
                <Text style={S.kpiSub}>vs. same period prior year</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: data.mom_growth >= 0 ? C.green : C.red }]}>
                <Text style={S.kpiLbl}>MoM GROWTH</Text>
                <Text style={[S.kpiVal, data.mom_growth >= 0 ? S.green : S.red]}>
                  {fmtGrowth(data.mom_growth)}
                </Text>
                <Text style={S.kpiSub}>vs. previous month</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: '#f59e0b' }]}>
                <Text style={S.kpiLbl}>MTD SALES</Text>
                <Text style={S.kpiVal}>{fmtM(data.mtd)}</Text>
                <Text style={S.kpiSub}>Month-to-date revenue</Text>
              </View>
            </View>
          </View>

          {/* Financial Summary table */}
          <View style={S.sec}>
            <Text style={S.secTitle}>FINANCIAL SUMMARY</Text>
            <View style={S.sBox}>
              {([
                ['Total All-Time Revenue',  fmtM(data.total)],
                ['Total All-Time Profit',   fmtM(data.total_profit)],
                ['Year-to-Date Revenue',    fmtM(data.ytd)],
                ['Year-to-Date Profit',     fmtM(data.ytd_profit)],
                ['Month-to-Date Revenue',   fmtM(data.mtd)],
                ['Month-to-Date Profit',    fmtM(data.mtd_profit)],
                ['Average Profit Margin',   fmtPct(data.avg_profit_margin)],
                ['YoY Growth Rate',         fmtGrowth(data.yoy_growth)],
                ['MoM Growth Rate',         fmtGrowth(data.mom_growth)],
                ['Last Data Update',        data.last_updated ?? 'N/A'],
              ] as [string, string][]).map(([lbl, val], i) => (
                <View key={i} style={S.sRow}>
                  <Text style={S.sLbl}>{lbl}</Text>
                  <Text style={S.sVal}>{val}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Channel breakdown */}
          {chData?.channels?.length ? (
            <View style={S.sec}>
              <Text style={S.secTitle}>SALES CHANNEL BREAKDOWN</Text>
              <View style={S.tbl}>
                <View style={S.tHead}>
                  <Text style={[S.tHCell, S.tHCL, { flex: 1.5 }]}>Channel</Text>
                  <Text style={S.tHCell}>Revenue</Text>
                  <Text style={S.tHCell}>Profit</Text>
                  <Text style={S.tHCell}>Transactions</Text>
                  <Text style={S.tHCell}>Share %</Text>
                </View>
                {chData.channels.map((ch, i) => (
                  <View key={i} style={[S.tRow, i % 2 === 1 ? S.tAlt : {}]}>
                    <Text style={[S.tCell, S.tCL, S.tBold, { flex: 1.5 }]}>{ch.channel}</Text>
                    <Text style={S.tCell}>{fmtM(ch.revenue)}</Text>
                    <Text style={S.tCell}>{fmtM(ch.profit)}</Text>
                    <Text style={S.tCell}>{ch.transactions.toLocaleString()}</Text>
                    <Text style={S.tCell}>{ch.share_pct.toFixed(1)}%</Text>
                  </View>
                ))}
              </View>
            </View>
          ) : null}
        </View>

        {/* Footer */}
        <View style={S.footer} fixed>
          <Text style={S.footerTxt}>Confidential – Internal Use Only  •  BI Dashboard</Text>
          <Text style={S.footerTxt} render={({ pageNumber, totalPages }) => `Page ${pageNumber} of ${totalPages}`} />
        </View>
      </Page>

      {/* ════════════════════════════════════════
          PAGE 2 – Trend & Store Data
          ════════════════════════════════════════ */}
      {(yearRows.length > 0 || pieRows.length > 0) && (
        <Page size="A4" style={S.page}>
          <View style={S.pHeader}>
            <Text style={S.pHeaderTitle}>Revenue Trend & Store Analysis</Text>
            <Text style={S.pHeaderSub}>Period: {filterLabel}</Text>
          </View>

          <View style={S.body}>
            {/* Annual trend table */}
            {yearRows.length > 0 && (
              <View style={S.sec}>
                <Text style={S.secTitle}>ANNUAL REVENUE TREND</Text>
                <View style={S.tbl}>
                  <View style={S.tHead}>
                    <Text style={[S.tHCell, S.tHCL]}>Year</Text>
                    <Text style={S.tHCell}>Revenue</Text>
                    <Text style={S.tHCell}>Profit</Text>
                    <Text style={S.tHCell}>Margin</Text>
                    <Text style={S.tHCell}>YoY Change</Text>
                  </View>
                  {yearRows.map((r, i) => {
                    const prev  = i > 0 ? yearRows[i - 1] : null;
                    const delta = prev ? ((r.sales - prev.sales) / prev.sales) * 100 : null;
                    return (
                      <View key={r.year} style={[S.tRow, i % 2 === 1 ? S.tAlt : {}]}>
                        <Text style={[S.tCell, S.tCL, S.tBold]}>{r.year}</Text>
                        <Text style={S.tCell}>{fmtM(r.sales)}</Text>
                        <Text style={S.tCell}>{fmtM(r.profit)}</Text>
                        <Text style={[S.tCell, { color: r.margin > 20 ? C.green : r.margin > 10 ? C.amber : C.red }]}>
                          {r.margin.toFixed(1)}%
                        </Text>
                        <Text style={[S.tCell, delta === null ? {} : { color: delta >= 0 ? C.green : C.red }]}>
                          {delta === null ? 'N/A' : fmtGrowth(delta)}
                        </Text>
                      </View>
                    );
                  })}
                </View>
              </View>
            )}

            {/* Store ranking table */}
            {pieRows.length > 0 && (
              <View style={S.sec}>
                <Text style={S.secTitle}>STORE PERFORMANCE RANKING</Text>
                <View style={S.tbl}>
                  <View style={S.tHead}>
                    <Text style={[S.tHCell, { flex: 0.4 }]}>#</Text>
                    <Text style={[S.tHCell, S.tHCL, { flex: 2.5 }]}>Store</Text>
                    <Text style={S.tHCell}>Revenue</Text>
                    <Text style={S.tHCell}>Share %</Text>
                  </View>
                  {(() => {
                    const total = pieRows.reduce((s, r) => s + r.value, 0);
                    return [...pieRows]
                      .sort((a, b) => b.value - a.value)
                      .map((r, i) => (
                        <View key={i} style={[S.tRow, i % 2 === 1 ? S.tAlt : {}]}>
                          <Text style={[S.tCell, { flex: 0.4 }]}>{i + 1}</Text>
                          <Text style={[S.tCell, S.tCL, { flex: 2.5 }]}>{r.name}</Text>
                          <Text style={S.tCell}>{fmtM(r.value)}</Text>
                          <Text style={S.tCell}>{total > 0 ? ((r.value / total) * 100).toFixed(1) : '0.0'}%</Text>
                        </View>
                      ));
                  })()}
                </View>
                {pieRows.length > 50 && (
                  <Text style={S.note}>* Showing top 50 stores by revenue. Total stores: {pieRows.length}.</Text>
                )}
              </View>
            )}
          </View>

          <View style={S.footer} fixed>
            <Text style={S.footerTxt}>Confidential – Internal Use Only  •  BI Dashboard</Text>
            <Text style={S.footerTxt} render={({ pageNumber, totalPages }) => `Page ${pageNumber} of ${totalPages}`} />
          </View>
        </Page>
      )}
    </Document>
  );
}

// ── Blob generator (call this via dynamic import to avoid SSR issues) ─────────
export async function generateSalesPDFBlob(props: SalesProfitPDFDocProps): Promise<Blob> {
  return pdf(<SalesProfitPDFDoc {...props} />).toBlob();
}
