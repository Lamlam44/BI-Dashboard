"use client";
import React, { useState, useEffect } from "react";
import DashboardLayout from "../components/DashboardLayout";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
  Area,
} from "recharts";

export default function ForecastingClient() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [productId, setProductId] = useState(310); // Standard demo ID
  const [forecastSteps, setForecastSteps] = useState(14);

  const fetchForecast = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `http://localhost:8000/forecast/${productId}?days_ahead=${forecastSteps}`,
      );
      if (!response.ok) {
        throw new Error(
          "Failed to fetch forecast data from backend. Make sure the FastAPI server is running on port 8000!",
        );
      }
      const rawData = await response.json();

      const points = Array.isArray(rawData)
        ? rawData
        : rawData.forecast_points || [];
      const formattedData = points.map((item: any) => ({
        date: (item.date || item.DateKey || "").split("T")[0],
        actual: item.actual != null ? parseFloat(item.actual) : null,
        predicted:
          item.predicted != null ? parseFloat(item.predicted.toFixed(2)) : null,
        lowerBound:
          item.lower_bound != null
            ? parseFloat(item.lower_bound.toFixed(2))
            : null,
        upperBound:
          item.upper_bound != null
            ? parseFloat(item.upper_bound.toFixed(2))
            : null,
      }));

      setData(formattedData);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchForecast();
  }, []);

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">
            AI Demand Forecasting
          </h1>
          <p className="text-slate-600 mt-2">
            Predictive analytics dynamically connected to the LightGBM Backend
          </p>
        </div>

        <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
          <div className="flex gap-4 items-end mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Product ID
              </label>
              <input
                type="number"
                value={productId}
                onChange={(e) => setProductId(Number(e.target.value))}
                className="border p-2 rounded w-32"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Days Ahead
              </label>
              <input
                type="number"
                value={forecastSteps}
                onChange={(e) => setForecastSteps(Number(e.target.value))}
                className="border p-2 rounded w-32"
                min="1"
                max="30"
              />
            </div>
            <button
              onClick={fetchForecast}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
            >
              {loading ? "Calculating..." : "Run AI Model"}
            </button>
          </div>

          {error && (
            <div className="bg-red-50 text-red-500 p-4 rounded mb-4 border border-red-200">
              {error}
            </div>
          )}

          <div style={{ width: "100%", height: 400 }}>
            {data.length > 0 && !loading && (
              <ResponsiveContainer>
                <ComposedChart
                  data={data}
                  margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="upperBound"
                    fill="#e2e8f0"
                    stroke="none"
                    fillOpacity={0.4}
                  />
                  <Area
                    type="monotone"
                    dataKey="lowerBound"
                    fill="#ffffff"
                    stroke="none"
                    fillOpacity={1}
                  />
                  <Line
                    type="monotone"
                    dataKey="predicted"
                    stroke="#3b82f6"
                    strokeWidth={3}
                    dot={{ r: 4 }}
                    activeDot={{ r: 8 }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            )}

            {data.length === 0 && !loading && !error && (
              <div className="h-full flex items-center justify-center text-gray-400">
                No data loaded yet.
              </div>
            )}

            {loading && (
              <div className="h-full flex flex-col items-center justify-center text-blue-500">
                <p className="text-xl font-semibold animate-pulse">
                  Running Multi-Step Recursive Forecasting...
                </p>
                <p className="text-sm mt-2 text-gray-500">
                  Processing Time Series Data in Backend
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
