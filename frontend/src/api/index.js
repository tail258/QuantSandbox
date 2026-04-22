import axios from 'axios';

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000/api', 
  timeout: 10000,
});

export const getSummary = (startDate, endDate) => {
  return api.get('/summary', {
    params: { start_date: startDate, end_date: endDate }
  });
};

export const getStockDetail = (ticker, startDate, endDate) => {
  return api.get(`/detail/${ticker}`, {
    params: { start_date: startDate, end_date: endDate }
  });
};

export default api;