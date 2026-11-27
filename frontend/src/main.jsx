import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import App from "./App.jsx";
import Home from "./pages/Home.jsx";
import IpoDetail from "./pages/IpoDetail.jsx";
import Report from "./pages/Report.jsx";
import Portfolio from "./pages/Portfolio.jsx";
import News from "./pages/News.jsx";
import Ipos from "./pages/Ipos.jsx";
import { Movers, Stocks } from "./pages/Stocks.jsx";
import "./layout.css";
import "./portfolio.css";
import "./styles.css";
import "./detail.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route path="/" element={<Home />} />
          <Route path="/report" element={<Report />} />
          <Route path="/ipo/:slug" element={<IpoDetail />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/news" element={<News />} />
          <Route path="/stocks" element={<Stocks />} />
          <Route path="/movers" element={<Movers />} />
          <Route path="/ipos" element={<Ipos />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
