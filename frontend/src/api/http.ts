import axios from 'axios'
import { apiBaseUrl } from './base'

const http = axios.create({
  baseURL: apiBaseUrl,
  withCredentials: true,
  timeout: 60000
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      window.location.hash = '#/login'
    }
    return Promise.reject(error)
  }
)

export default http
