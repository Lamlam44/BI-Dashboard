'use client';

/**
 * EmployeePDFDoc
 * --------------
 * @react-pdf/renderer document for Employee Performance dashboard.
 * Pages:
 *   Page 1 – KPI Summary + Top Performer + Capabilities
 *   Page 2 – Leaderboard table + Trend table
 */

import React from 'react';
import {
  Document, Font, Page, StyleSheet, Text, View, pdf,
} from '@react-pdf/renderer';
import type {
  DashboardResponse,
  LeaderboardResponse,
  TrendResponse,
} from '../../employee-performance/components/types';

const _FONT_ORIGIN =
  typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000';

Font.register({
  family: 'NotoSans',
  fonts: [
    { src: `${_FONT_ORIGIN}/fonts/NotoSans-Regular.ttf`, fontWeight: 'normal' },
    { src: `${_FONT_ORIGIN}/fonts/NotoSans-Bold.ttf`, fontWeight: 'bold' },
  ],
});

const FONT   = 'NotoSans';
const FONT_B = 'NotoSans';

export interface EmployeePDFDocProps {
  dashboard?: DashboardResponse | null;
  leaderboard?: LeaderboardResponse | null;
  trend?: TrendResponse | null;
  filterLabel: string;
  username?: string;
}

// ── Formatters ────────────────────────────────────────────────────────────────
const fmtM = (v: number) => {
  const n = v ?? 0;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);
};
const fmtPct = (v?: number | null) => v != null ? `${(v * 100).toFixed(1)}%` : 'N/A';
const fmtNum = (v?: number | null) => v != null ? new Intl.NumberFormat('en-US').format(v) : 'N/A';

const C = {
  navyBg: '#1e3a5f', navyText: '#ffffff', navySub: '#93c5fd', navyBdr: '#3b82f6',
  accent: '#2563eb', slate9: '#0f172a', slate7: '#334155', slate5: '#64748b',
  slate3: '#cbd5e1', slate2: '#e2e8f0', slate1: '#f1f5f9', white: '#ffffff',
  green: '#15803d', red: '#b91c1c', amber: '#b45309',
};

const S = StyleSheet.create({
  page: { fontFamily: FONT, paddingBottom: 44, backgroundColor: '#f8fafc' },

  cHeader:  { backgroundColor: C.navyBg, padding: '28 36 20 36', marginBottom: 24 },
  cTitle:   { fontSize: 20, fontFamily: FONT_B, fontWeight: 'bold', color: C.navyText, marginBottom: 4 },
  cSub:     { fontSize: 10, color: C.navySub, marginBottom: 14 },
  cMetaRow: { flexDirection: 'row', justifyContent: 'space-between', borderTopWidth: 1, borderTopColor: C.navyBdr, paddingTop: 8 },
  cMeta:    { fontSize: 8, color: '#cbd5e1' },

  pHeader:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: C.navyBg, padding: '10 36', marginBottom: 18 },
  pHeaderTitle: { fontSize: 10, fontFamily: FONT_B, fontWeight: 'bold', color: C.navyText },
  pHeaderSub:   { fontSize: 8, color: C.navySub },

  body:     { paddingHorizontal: 36 },
  sec:      { marginBottom: 16 },
  secTitle: { fontSize: 9, fontFamily: FONT_B, fontWeight: 'bold', color: C.navyText, backgroundColor: C.accent, padding: '5 10', marginBottom: 10, borderRadius: 2 },

  kpiRow:  { flexDirection: 'row', gap: 8, marginBottom: 8 },
  kpiCard: { flex: 1, backgroundColor: C.white, border: 1, borderColor: C.slate2, borderRadius: 4, padding: '8 10', borderTopWidth: 3, borderTopColor: C.accent },
  kpiLbl:  { fontSize: 7, color: C.slate5, marginBottom: 4 },
  kpiVal:  { fontSize: 13, fontFamily: FONT_B, fontWeight: 'bold', color: C.slate9 },
  kpiSub:  { fontSize: 7, color: C.slate5, marginTop: 2 },
  green:   { color: C.green },
  red:     { color: C.red },

  sBox: { backgroundColor: C.white, border: 1, borderColor: C.slate2, borderRadius: 4, padding: 12, marginBottom: 10 },
  sRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3, borderBottomWidth: 0.5, borderBottomColor: C.slate2 },
  sLbl: { fontSize: 8, color: C.slate5 },
  sVal: { fontSize: 8, fontFamily: FONT_B, fontWeight: 'bold', color: C.slate7 },

  tbl:    { width: '100%', marginBottom: 4 },
  tHead:  { flexDirection: 'row', backgroundColor: '#1e40af', padding: '5 0', borderRadius: 2 },
  tHCell: { fontSize: 8, fontFamily: FONT_B, fontWeight: 'bold', color: C.white, paddingHorizontal: 6, flex: 1, textAlign: 'center' },
  tHCL:   { textAlign: 'left' },
  tRow:   { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: C.slate2, paddingVertical: 4 },
  tAlt:   { backgroundColor: C.slate1 },
  tCell:  { fontSize: 8, color: C.slate7, paddingHorizontal: 6, flex: 1, textAlign: 'center' },
  tCL:    { textAlign: 'left' },
  tBold:  { fontFamily: FONT_B, fontWeight: 'bold' },

  capRow:  { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  capTag:  { fontSize: 7, padding: '3 7', borderRadius: 10, backgroundColor: '#dcfce7', color: C.green },
  capTagN: { fontSize: 7, padding: '3 7', borderRadius: 10, backgroundColor: C.slate1, color: C.slate5 },

  footer:    { position: 'absolute', bottom: 14, left: 36, right: 36, flexDirection: 'row', justifyContent: 'space-between', borderTopWidth: 0.5, borderTopColor: C.slate3, paddingTop: 4 },
  footerTxt: { fontSize: 7, color: '#94a3b8' },
});

// ── Component ─────────────────────────────────────────────────────────────────
export function EmployeePDFDoc({ dashboard, leaderboard, trend, filterLabel, username }: EmployeePDFDocProps) {
  const generated = new Date().toLocaleString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
  const kpis = dashboard?.kpis;
  const top  = dashboard?.top_performer;

  return (
    <Document
      title="Employee Performance Report"
      author={username ?? 'BI Dashboard'}
      subject={`Period: ${filterLabel}`}
      creator="BI Dashboard System"
    >
      {/* ════════════ PAGE 1 – KPI Summary ════════════ */}
      <Page size="A4" style={S.page}>
        <View style={S.cHeader}>
          <Text style={S.cTitle}>Employee Performance Report</Text>
          <Text style={S.cSub}>Business Intelligence Dashboard – Store Performance Analytics</Text>
          <View style={S.cMetaRow}>
            <Text style={S.cMeta}>Period: {filterLabel}</Text>
            <Text style={S.cMeta}>Generated: {generated}</Text>
            {username && <Text style={S.cMeta}>User: {username}</Text>}
          </View>
        </View>

        <View style={S.body}>
          {/* KPI cards */}
          <View style={S.sec}>
            <Text style={S.secTitle}>KEY PERFORMANCE METRICS</Text>
            <View style={S.kpiRow}>
              <View style={[S.kpiCard, { borderTopColor: '#2563eb' }]}>
                <Text style={S.kpiLbl}>TOTAL NET SALES</Text>
                <Text style={S.kpiVal}>{fmtM(kpis?.total_net_sales ?? 0)}</Text>
                <Text style={S.kpiSub}>Net after returns & discounts</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: '#16a34a' }]}>
                <Text style={S.kpiLbl}>AVG PROFIT MARGIN</Text>
                <Text style={[S.kpiVal, { color: (kpis?.avg_profit_margin ?? 0) >= 0.2 ? C.green : C.red }]}>
                  {fmtPct(kpis?.avg_profit_margin)}
                </Text>
                <Text style={S.kpiSub}>Across filtered employees</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: '#f59e0b' }]}>
                <Text style={S.kpiLbl}>TOTAL ORDERS</Text>
                <Text style={S.kpiVal}>{fmtNum(kpis?.total_orders)}</Text>
                <Text style={S.kpiSub}>Transactions in period</Text>
              </View>
            </View>
            <View style={S.kpiRow}>
              <View style={[S.kpiCard, { borderTopColor: '#8b5cf6' }]}>
                <Text style={S.kpiLbl}>AVG TICKET SIZE</Text>
                <Text style={S.kpiVal}>{fmtM(kpis?.avg_ticket_size ?? 0)}</Text>
                <Text style={S.kpiSub}>Revenue per order</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: '#ec4899' }]}>
                <Text style={S.kpiLbl}>AVG RETURN RATE</Text>
                <Text style={[S.kpiVal, { color: (kpis?.avg_return_rate ?? 0) > 0.05 ? C.red : C.green }]}>
                  {fmtPct(kpis?.avg_return_rate)}
                </Text>
                <Text style={S.kpiSub}>Lower is better</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: '#14b8a6' }]}>
                <Text style={S.kpiLbl}>EMPLOYEE COUNT</Text>
                <Text style={S.kpiVal}>{fmtNum(kpis?.employee_count)}</Text>
                <Text style={S.kpiSub}>Active in filter period</Text>
              </View>
            </View>
          </View>

          {/* Top Performer */}
          {top && (
            <View style={S.sec}>
              <Text style={S.secTitle}>TOP PERFORMER</Text>
              <View style={S.sBox}>
                {([
                  ['Name',          top.employee_name],
                  ['Title',         top.title ?? 'N/A'],
                  ['Net Sales',     fmtM(top.net_sales)],
                  ['Profit Margin', fmtPct(top.profit_margin)],
                  ['Return Rate',   fmtPct(top.return_rate)],
                  ['Total Orders',  fmtNum(top.total_orders)],
                ] as [string, string][]).map(([lbl, val], i) => (
                  <View key={i} style={S.sRow}>
                    <Text style={S.sLbl}>{lbl}</Text>
                    <Text style={S.sVal}>{val}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* Capability flags */}
          {dashboard?.capabilities?.length ? (
            <View style={S.sec}>
              <Text style={S.secTitle}>DATA AVAILABILITY</Text>
              <View style={S.capRow}>
                {dashboard.capabilities.map((c, i) => (
                  <Text key={i} style={c.enabled ? S.capTag : S.capTagN}>
                    {c.enabled ? '✓' : '○'} {c.key.replace(/_/g, ' ')}
                  </Text>
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

      {/* ════════════ PAGE 2 – Leaderboard + Trend ════════════ */}
      {((leaderboard?.rows?.length ?? 0) > 0 || (trend?.rows?.length ?? 0) > 0) && (
        <Page size="A4" style={S.page}>
          <View style={S.pHeader}>
            <Text style={S.pHeaderTitle}>Leaderboard & Performance Trend</Text>
            <Text style={S.pHeaderSub}>Period: {filterLabel}</Text>
          </View>

          <View style={S.body}>
            {/* Leaderboard */}
            {(leaderboard?.rows?.length ?? 0) > 0 && (
              <View style={S.sec}>
                <Text style={S.secTitle}>EMPLOYEE LEADERBOARD (ALL {leaderboard!.rows.length} EMPLOYEES)</Text>
                <View style={S.tbl}>
                  <View style={S.tHead}>
                    <Text style={[S.tHCell, { flex: 0.4 }]}>#</Text>
                    <Text style={[S.tHCell, S.tHCL, { flex: 2 }]}>Employee</Text>
                    <Text style={S.tHCell}>Net Sales</Text>
                    <Text style={S.tHCell}>Margin</Text>
                    <Text style={S.tHCell}>Orders</Text>
                    <Text style={S.tHCell}>Return %</Text>
                  </View>
                  {leaderboard!.rows.map((r, i) => (
                    <View key={r.employee_key} style={[S.tRow, i % 2 === 1 ? S.tAlt : {}]}>
                      <Text style={[S.tCell, { flex: 0.4 }]}>{r.ranking}</Text>
                      <Text style={[S.tCell, S.tCL, S.tBold, { flex: 2 }]}>{r.employee_name}</Text>
                      <Text style={S.tCell}>{fmtM(r.net_sales)}</Text>
                      <Text style={[S.tCell, { color: r.profit_margin >= 0.2 ? C.green : C.red }]}>
                        {fmtPct(r.profit_margin)}
                      </Text>
                      <Text style={S.tCell}>{fmtNum(r.total_orders)}</Text>
                      <Text style={[S.tCell, { color: r.return_rate > 0.05 ? C.red : C.green }]}>
                        {fmtPct(r.return_rate)}
                      </Text>
                    </View>
                  ))}
                </View>
              </View>
            )}

            {/* Trend table */}
            {(trend?.rows?.length ?? 0) > 0 && (
              <View style={S.sec}>
                <Text style={S.secTitle}>PERFORMANCE TREND BY PERIOD</Text>
                <View style={S.tbl}>
                  <View style={S.tHead}>
                    <Text style={[S.tHCell, S.tHCL]}>Year</Text>
                    <Text style={[S.tHCell, S.tHCL]}>Month</Text>
                    <Text style={S.tHCell}>Net Sales</Text>
                    <Text style={S.tHCell}>Margin</Text>
                    <Text style={S.tHCell}>Orders</Text>
                    <Text style={S.tHCell}>Return %</Text>
                  </View>
                  {trend!.rows.map((r, i) => (
                    <View key={i} style={[S.tRow, i % 2 === 1 ? S.tAlt : {}]}>
                      <Text style={[S.tCell, S.tCL, S.tBold]}>{r.year}</Text>
                      <Text style={[S.tCell, S.tCL]}>{r.month}</Text>
                      <Text style={S.tCell}>{fmtM(r.net_sales)}</Text>
                      <Text style={[S.tCell, { color: r.profit_margin >= 0.2 ? C.green : C.red }]}>
                        {fmtPct(r.profit_margin)}
                      </Text>
                      <Text style={S.tCell}>{fmtNum(r.total_orders)}</Text>
                      <Text style={[S.tCell, { color: r.return_rate > 0.05 ? C.red : C.green }]}>
                        {fmtPct(r.return_rate)}
                      </Text>
                    </View>
                  ))}
                </View>
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

// ── Blob generator (call via dynamic import to avoid SSR issues) ───────────
export async function generateEmployeePDFBlob(props: EmployeePDFDocProps): Promise<Blob> {
  return pdf(<EmployeePDFDoc {...props} />).toBlob();
}
