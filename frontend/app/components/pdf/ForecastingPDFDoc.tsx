'use client';

/**
 * ForecastingPDFDoc
 * -----------------
 * @react-pdf/renderer document for the AI Demand Forecasting page.
 * Shows ALL data – no row limits.
 *
 * Pages:
 *   Page 1 – Overview KPIs + ABC/XYZ distribution
 *   Page 2 – Demand Alerts (hotspots)
 *   Page 3+ – Full SKU list from bulkRows (all rows, paginated by @react-pdf/renderer)
 */

import React from 'react';
import {
  Document, Font, Page, StyleSheet, Text, View, pdf,
} from '@react-pdf/renderer';

const _FONT_ORIGIN =
  typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000';

Font.register({
  family: 'NotoSans',
  fonts: [
    { src: `${_FONT_ORIGIN}/fonts/NotoSans-Regular.ttf`, fontWeight: 'normal' },
    { src: `${_FONT_ORIGIN}/fonts/NotoSans-Bold.ttf`, fontWeight: 'bold' },
  ],
});

const FONT  = 'NotoSans';
const FONT_B = 'NotoSans';

// ── Types (imported from forecasting client-page.tsx) ─────────────────────────
export interface OverviewResponse {
  forecast_total_demand: number;
  sku_count: number;
  abc_distribution: Record<string, number>;
  xyz_distribution: Record<string, number>;
  avg_daily_demand: number;
  horizon_days: number;
  last_data_date: string;
}

export interface AlertRow {
  product_id: number;
  product_name: string;
  abc_class: string;
  xyz_class: string;
  mean_14: number;
  mean_90: number;
  spike_score: number;
  message: string;
}

export interface BulkRow {
  product_id: number;
  product_name: string;
  category_key: number;
  abc_class: string;
  xyz_class: string;
  revenue: number;
  cv: number;
}

export interface ForecastingPDFDocProps {
  overview?: OverviewResponse | null;
  alerts: AlertRow[];
  bulkRows: BulkRow[];
  abcFilter: string;
  xyzFilter: string;
  horizonDays: number;
  username?: string;
}

// ── Color palette ─────────────────────────────────────────────────────────────
const C = {
  navyBg: '#1e3a5f', navyText: '#ffffff', navySub: '#93c5fd', navyBdr: '#3b82f6',
  accent: '#2563eb', slate9: '#0f172a', slate7: '#334155', slate5: '#64748b',
  slate3: '#cbd5e1', slate2: '#e2e8f0', slate1: '#f1f5f9', white: '#ffffff',
  green: '#15803d', red: '#b91c1c', amber: '#b45309',
  emerald: '#065f46', rose: '#9f1239',
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

  distRow: { flexDirection: 'row', gap: 16, marginBottom: 10 },
  distBox: { flex: 1, backgroundColor: C.white, border: 1, borderColor: C.slate2, borderRadius: 4, padding: '8 10' },
  distLbl: { fontSize: 8, fontFamily: FONT_B, fontWeight: 'bold', color: C.slate7, marginBottom: 6 },
  distItem:{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 2 },
  distKey: { fontSize: 8, color: C.slate5 },
  distVal: { fontSize: 8, fontFamily: FONT_B, fontWeight: 'bold', color: C.slate9 },

  tbl:    { width: '100%', marginBottom: 4 },
  tHead:  { flexDirection: 'row', backgroundColor: '#1e40af', padding: '5 0', borderRadius: 2 },
  tHCell: { fontSize: 8, fontFamily: FONT_B, fontWeight: 'bold', color: C.white, paddingHorizontal: 6, flex: 1, textAlign: 'center' },
  tHCL:   { textAlign: 'left' },
  tRow:   { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: C.slate2, paddingVertical: 4 },
  tAlt:   { backgroundColor: C.slate1 },
  tCell:  { fontSize: 8, color: C.slate7, paddingHorizontal: 6, flex: 1, textAlign: 'center' },
  tCL:    { textAlign: 'left' },
  tBold:  { fontFamily: FONT_B, fontWeight: 'bold' },

  badge:  { fontSize: 7, padding: '2 6', borderRadius: 8, textAlign: 'center' },
  badgeA: { backgroundColor: '#fef9c3', color: '#854d0e' },
  badgeB: { backgroundColor: '#dbeafe', color: '#1e40af' },
  badgeC: { backgroundColor: '#dcfce7', color: '#166534' },
  badgeX: { backgroundColor: '#fee2e2', color: '#991b1b' },
  badgeY: { backgroundColor: '#fef3c7', color: '#92400e' },
  badgeZ: { backgroundColor: '#ede9fe', color: '#5b21b6' },

  spikeHigh:   { color: C.red, fontFamily: FONT_B, fontWeight: 'bold' },
  spikeMed:    { color: C.amber },
  spikeLow:    { color: C.green },

  footer:    { position: 'absolute', bottom: 14, left: 36, right: 36, flexDirection: 'row', justifyContent: 'space-between', borderTopWidth: 0.5, borderTopColor: C.slate3, paddingTop: 4 },
  footerTxt: { fontSize: 7, color: '#94a3b8' },
  note:      { fontSize: 7, color: C.slate5, marginTop: 6 },
});

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmtN  = (v: number) => new Intl.NumberFormat('en-US').format(Math.round(v ?? 0));
const fmtR  = (v: number) => (v ?? 0).toFixed(3);
const fmtM  = (v: number) => {
  const n = v ?? 0;
  if (Math.abs(n) >= 1e9) return `$${(n/1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n/1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n/1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
};

const Footer = () => (
  <View style={S.footer} fixed>
    <Text style={S.footerTxt}>Confidential – Internal Use Only  •  BI Dashboard</Text>
    <Text style={S.footerTxt} render={({ pageNumber, totalPages }) => `Page ${pageNumber} of ${totalPages}`} />
  </View>
);

// ── Main Document ─────────────────────────────────────────────────────────────
export function ForecastingPDFDoc({
  overview, alerts, bulkRows, abcFilter, xyzFilter, horizonDays, username,
}: ForecastingPDFDocProps) {
  const generated = new Date().toLocaleString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
  const filterDesc = [
    `Horizon: ${horizonDays} days`,
    abcFilter !== 'ALL' ? `ABC: ${abcFilter}` : 'ABC: All',
    xyzFilter !== 'ALL' ? `XYZ: ${xyzFilter}` : 'XYZ: All',
  ].join('  |  ');

  return (
    <Document
      title="Demand Forecasting Report"
      author={username ?? 'BI Dashboard'}
      subject={filterDesc}
      creator="BI Dashboard System"
    >
      {/* ══════════════════════════════════════════
          PAGE 1 – Overview + Distributions
          ══════════════════════════════════════════ */}
      <Page size="A4" style={S.page}>
        <View style={S.cHeader}>
          <Text style={S.cTitle}>Demand Forecast Report</Text>
          <Text style={S.cSub}>AI-Powered Demand Forecasting – Control Tower</Text>
          <View style={S.cMetaRow}>
            <Text style={S.cMeta}>{filterDesc}</Text>
            <Text style={S.cMeta}>Generated: {generated}</Text>
            {username && <Text style={S.cMeta}>User: {username}</Text>}
          </View>
        </View>

        <View style={S.body}>
          {/* Overview KPIs */}
          <View style={S.sec}>
            <Text style={S.secTitle}>FORECAST OVERVIEW</Text>
            <View style={S.kpiRow}>
              <View style={[S.kpiCard, { borderTopColor: '#2563eb' }]}>
                <Text style={S.kpiLbl}>FORECAST TOTAL DEMAND</Text>
                <Text style={S.kpiVal}>{fmtN(overview?.forecast_total_demand ?? 0)}</Text>
                <Text style={S.kpiSub}>Next {horizonDays} days</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: '#7c3aed' }]}>
                <Text style={S.kpiLbl}>SKU COUNT</Text>
                <Text style={S.kpiVal}>{fmtN(overview?.sku_count ?? 0)}</Text>
                <Text style={S.kpiSub}>Active products</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: '#0891b2' }]}>
                <Text style={S.kpiLbl}>AVG DAILY DEMAND</Text>
                <Text style={S.kpiVal}>{fmtN(overview?.avg_daily_demand ?? 0)}</Text>
                <Text style={S.kpiSub}>Units/day average</Text>
              </View>
            </View>
            <View style={S.kpiRow}>
              <View style={[S.kpiCard, { borderTopColor: '#16a34a', flex: 2 }]}>
                <Text style={S.kpiLbl}>FORECAST HORIZON</Text>
                <Text style={S.kpiVal}>{horizonDays} days</Text>
                <Text style={S.kpiSub}>Last data: {overview?.last_data_date ?? 'N/A'}</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: '#dc2626' }]}>
                <Text style={S.kpiLbl}>ALERTS</Text>
                <Text style={[S.kpiVal, { color: alerts.length > 0 ? C.red : C.green }]}>{alerts.length}</Text>
                <Text style={S.kpiSub}>Demand spikes detected</Text>
              </View>
              <View style={[S.kpiCard, { borderTopColor: '#f59e0b' }]}>
                <Text style={S.kpiLbl}>FILTERED SKUs</Text>
                <Text style={S.kpiVal}>{fmtN(bulkRows.length)}</Text>
                <Text style={S.kpiSub}>In current filter</Text>
              </View>
            </View>
          </View>

          {/* ABC + XYZ distribution */}
          {overview && (
            <View style={S.sec}>
              <Text style={S.secTitle}>ABC / XYZ CLASSIFICATION DISTRIBUTION</Text>
              <View style={S.distRow}>
                {/* ABC */}
                <View style={S.distBox}>
                  <Text style={S.distLbl}>ABC Distribution</Text>
                  {Object.entries(overview.abc_distribution ?? {}).map(([cls, cnt]) => (
                    <View key={cls} style={S.distItem}>
                      <Text style={S.distKey}>Class {cls}</Text>
                      <Text style={S.distVal}>{fmtN(cnt)} SKUs</Text>
                    </View>
                  ))}
                </View>
                {/* XYZ */}
                <View style={S.distBox}>
                  <Text style={S.distLbl}>XYZ Distribution</Text>
                  {Object.entries(overview.xyz_distribution ?? {}).map(([cls, cnt]) => (
                    <View key={cls} style={S.distItem}>
                      <Text style={S.distKey}>Class {cls}</Text>
                      <Text style={S.distVal}>{fmtN(cnt)} SKUs</Text>
                    </View>
                  ))}
                </View>
              </View>
            </View>
          )}
        </View>
        <Footer />
      </Page>

      {/* ══════════════════════════════════════════
          PAGE 2 – Demand Alerts (Hotspots)
          ══════════════════════════════════════════ */}
      <Page size="A4" style={S.page}>
        <View style={S.pHeader}>
          <Text style={S.pHeaderTitle}>Demand Alerts – Hotspots</Text>
          <Text style={S.pHeaderSub}>{filterDesc}</Text>
        </View>
        <View style={S.body}>
          <View style={S.sec}>
            <Text style={S.secTitle}>DEMAND SPIKE ALERTS ({alerts.length} ITEMS)</Text>
            {alerts.length > 0 ? (
              <View style={S.tbl}>
                <View style={S.tHead}>
                  <Text style={[S.tHCell, { flex: 0.6 }]}>SKU</Text>
                  <Text style={[S.tHCell, S.tHCL, { flex: 2.5 }]}>Product</Text>
                  <Text style={[S.tHCell, { flex: 0.7 }]}>Class</Text>
                  <Text style={S.tHCell}>14d Mean</Text>
                  <Text style={S.tHCell}>90d Mean</Text>
                  <Text style={S.tHCell}>Spike Score</Text>
                </View>
                {alerts.map((r, i) => (
                  <View key={r.product_id} style={[S.tRow, i % 2 === 1 ? S.tAlt : {}]}>
                    <Text style={[S.tCell, { flex: 0.6 }]}>{r.product_id}</Text>
                    <Text style={[S.tCell, S.tCL, S.tBold, { flex: 2.5 }]}>{r.product_name}</Text>
                    <Text style={[S.tCell, { flex: 0.7 }]}>{r.abc_class}/{r.xyz_class}</Text>
                    <Text style={S.tCell}>{r.mean_14.toFixed(2)}</Text>
                    <Text style={S.tCell}>{r.mean_90.toFixed(2)}</Text>
                    <Text style={[S.tCell,
                      r.spike_score >= 3 ? S.spikeHigh : r.spike_score >= 2 ? S.spikeMed : S.spikeLow,
                    ]}>
                      {r.spike_score.toFixed(2)}
                    </Text>
                  </View>
                ))}
              </View>
            ) : (
              <Text style={S.note}>No demand spike alerts detected for the selected filters.</Text>
            )}
          </View>
        </View>
        <Footer />
      </Page>

      {/* ══════════════════════════════════════════
          PAGE 3+ – Full SKU List (ALL bulkRows)
          ══════════════════════════════════════════ */}
      <Page size="A4" style={S.page}>
        <View style={S.pHeader} fixed>
          <Text style={S.pHeaderTitle}>SKU List – Bulk Filter Results</Text>
          <Text style={S.pHeaderSub}>{filterDesc}  |  {bulkRows.length} SKUs</Text>
        </View>
        <View style={S.body}>
          <View style={S.sec}>
            <Text style={S.secTitle}>
              COMPLETE SKU LIST – ABC: {abcFilter}  |  XYZ: {xyzFilter}  |  TOTAL: {bulkRows.length} SKUs
            </Text>
            <View style={S.tbl}>
              <View style={S.tHead} fixed>
                <Text style={[S.tHCell, { flex: 0.6 }]}>SKU</Text>
                <Text style={[S.tHCell, S.tHCL, { flex: 2.8 }]}>Product Name</Text>
                <Text style={[S.tHCell, { flex: 0.5 }]}>Cat.</Text>
                <Text style={[S.tHCell, { flex: 0.6 }]}>ABC</Text>
                <Text style={[S.tHCell, { flex: 0.6 }]}>XYZ</Text>
                <Text style={S.tHCell}>Revenue</Text>
                <Text style={S.tHCell}>CV</Text>
              </View>
              {bulkRows.map((r, i) => (
                <View key={r.product_id} style={[S.tRow, i % 2 === 1 ? S.tAlt : {}]} wrap={false}>
                  <Text style={[S.tCell, { flex: 0.6 }]}>{r.product_id}</Text>
                  <Text style={[S.tCell, S.tCL, S.tBold, { flex: 2.8 }]}>{r.product_name}</Text>
                  <Text style={[S.tCell, { flex: 0.5 }]}>{r.category_key}</Text>
                  <Text style={[S.tCell, { flex: 0.6 },
                    r.abc_class === 'A' ? S.badgeA : r.abc_class === 'B' ? S.badgeB : S.badgeC,
                  ]}>{r.abc_class}</Text>
                  <Text style={[S.tCell, { flex: 0.6 },
                    r.xyz_class === 'X' ? S.badgeX : r.xyz_class === 'Y' ? S.badgeY : S.badgeZ,
                  ]}>{r.xyz_class}</Text>
                  <Text style={S.tCell}>{fmtM(r.revenue)}</Text>
                  <Text style={S.tCell}>{fmtR(r.cv)}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>
        <Footer />
      </Page>
    </Document>
  );
}

// ── Blob generator (call via dynamic import to avoid SSR issues) ──────────────
export async function generateForecastPDFBlob(props: ForecastingPDFDocProps): Promise<Blob> {
  return pdf(<ForecastingPDFDoc {...props} />).toBlob();
}
