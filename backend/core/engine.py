import pandas as pd
import numpy as np

class BacktestEngine:
    """专业级向量化与事件混合回测引擎"""
    def __init__(self, initial_cash=100000.0, commission_rate=0.00025, tax_rate=0.0005):
        self.initial_cash = initial_cash
        self.commission = commission_rate  
        self.tax = tax_rate                
        self.logs = []                     

    def run(self, df: pd.DataFrame, symbol: str):
        cash = self.initial_cash
        shares = 0
        equity_curve = []
        self.logs = []
        
        # 记录每笔闭环交易的收益率，用于计算胜率和盈亏比
        trade_returns = []
        entry_price = 0.0 

        for i in range(len(df)):
            row = df.iloc[i]
            current_price = row['open']  
            signal = row['trade_signal']
            date_str = row['date'].strftime('%Y-%m-%d')

            # --- 交易撮合逻辑 ---
            # 1. 买入
            if signal == 1 and shares == 0:
                shares_to_buy = int(cash / (current_price * (1 + self.commission)) // 100 * 100)
                if shares_to_buy > 0:
                    cost = shares_to_buy * current_price * (1 + self.commission)
                    cash -= cost
                    shares = shares_to_buy
                    entry_price = current_price # 记录开仓成本价
                    self._add_log(date_str, symbol, "买入", current_price, shares, cost * self.commission, "策略买入信号")

            # 2. 卖出 (形成一次闭环交易)
            elif signal == -1 and shares > 0:
                revenue = shares * current_price * (1 - self.commission - self.tax)
                fee = shares * current_price * (self.commission + self.tax)
                
                # 计算这单交易的绝对净利润率
                trade_return = (revenue - (shares * entry_price)) / (shares * entry_price)
                trade_returns.append(trade_return)

                cash += revenue
                self._add_log(date_str, symbol, "卖出", current_price, shares, fee, "策略卖出信号")
                shares = 0
                entry_price = 0.0

            # --- 每日净值快照 ---
            daily_equity = cash + shares * row['close']
            equity_curve.append(daily_equity)

        # 将资金曲线写入 Dataframe 给前端画图
        df['total_equity'] = equity_curve
        
        # 计算高阶金融指标
        metrics = self._calculate_metrics(df, trade_returns, symbol)
        
        return {
            "metadata": metrics, # 包含了完整的战报指标
            "data": df,          # 包含了 K 线和 资金曲线 (total_equity)
            "logs": self.logs
        }

    def _calculate_metrics(self, df, trade_returns, symbol):
        """核心金融数学计算模块"""
        equity_series = df['total_equity']
        final_equity = equity_series.iloc[-1] if not equity_series.empty else self.initial_cash
        
        # 1. 累计收益率
        total_return = (final_equity - self.initial_cash) / self.initial_cash
        
        # 2. 最大回撤 (Max Drawdown) - 机构最看重的风控指标
        rolling_max = equity_series.cummax()
        drawdowns = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdowns.min() if not drawdowns.empty else 0
        
        # 3. 夏普比率 (Sharpe Ratio) - 衡量性价比 (假设无风险利率为0)
        df['daily_return'] = equity_series.pct_change().fillna(0)
        mean_return = df['daily_return'].mean()
        std_return = df['daily_return'].std()
        # 乘以根号252将日夏普年化
        sharpe = (mean_return / std_return) * np.sqrt(252) if std_return > 0 else 0
        
        # 4. 胜率 (Win Rate) & 盈亏比 (PnL Ratio)
        win_rate, pnl_ratio = 0.0, 0.0
        if trade_returns:
            winning_trades = [r for r in trade_returns if r > 0]
            losing_trades = [r for r in trade_returns if r <= 0]
            
            win_rate = len(winning_trades) / len(trade_returns)
            
            avg_win = np.mean(winning_trades) if winning_trades else 0
            avg_loss = abs(np.mean(losing_trades)) if losing_trades else 0
            
            if avg_loss > 0:
                pnl_ratio = avg_win / avg_loss
            elif avg_win > 0:
                pnl_ratio = 99.9 # 全胜无败的情况

        return {
            "symbol": symbol,
            "final_equity": round(final_equity, 2),
            "total_return": round(total_return * 100, 2),
            "max_drawdown": round(max_drawdown * 100, 2),
            "sharpe_ratio": round(sharpe, 2),
            "win_rate": round(win_rate * 100, 2),
            "pnl_ratio": round(pnl_ratio, 2),
            "trade_count": len(trade_returns)
        }

    def _add_log(self, date, ticker, action, price, shares, fee, reason):
        self.logs.append({
            "timestamp": date, "ticker": ticker, "action": action,
            "price": round(price, 2), "shares": shares, "fee": round(fee, 2), "reason": reason
        })