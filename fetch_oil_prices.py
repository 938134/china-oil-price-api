#!/usr/bin/env python3
"""
中国油价数据抓取脚本 - 修复版
使用有效的解析方法从油价网站获取数据
"""

import requests
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import time
import re

class ChinaOilPriceAPI:
    def __init__(self):
        # 从配置文件加载省份数据
        with open('provinces.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.provinces = config['provinces']
        
    def fetch_all_prices(self):
        """抓取所有省份油价数据"""
        all_data = {}
        success_count = 0
        
        for province_name, province_code in self.provinces.items():
            print(f"🔄 正在抓取 {province_name} 油价数据...")
            
            try:
                province_data = self.fetch_province_price(province_name, province_code)
                all_data[province_name] = province_data
                
                if province_data['status'] == 'success':
                    success_count += 1
                    print(f"✅ {province_name} 数据获取成功")
                    print(f"   92#: {province_data['prices'].get('92', '--')}")
                    print(f"   95#: {province_data['prices'].get('95', '--')}")
                    print(f"   98#: {province_data['prices'].get('98', '--')}")
                    print(f"   0#: {province_data['prices'].get('0', '--')}")
                else:
                    print(f"❌ {province_name} 数据获取失败: {province_data['error']['message']}")
                    
            except Exception as e:
                error_data = self._create_error_data(province_name, province_code, f"抓取异常: {str(e)}")
                all_data[province_name] = error_data
                print(f"❌ {province_name} 抓取异常: {str(e)}")
            
            # 礼貌性延迟，避免请求过快
            time.sleep(2)
        
        return self._create_final_output(all_data, success_count)
    
    def fetch_province_price(self, province_name, province_code):
        """抓取单个省份油价数据 - 使用有效的解析方法"""
        try:
            url = f'http://www.qiyoujiage.com/{province_code}.shtml'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                return self._create_error_data(province_name, province_code, f"HTTP状态码: {response.status_code}")
            
            html = response.text
            doc = BeautifulSoup(html, 'html.parser')
            
            # 使用有效的解析方法
            entries = {}
            
            # 方法1: 解析 #youjia > dl 结构
            oil_elements = doc.select('#youjia > dl')
            for dl in oil_elements:
                dt_text = dl.select_one('dt')
                dd_text = dl.select_one('dd')
                
                if dt_text and dd_text:
                    oil_type = dt_text.get_text().strip()
                    price_text = dd_text.get_text().strip()
                    
                    # 提取油品类型编号
                    oil_match = re.search(r'(\d+)', oil_type)
                    if oil_match:
                        oil_key = oil_match.group(1)
                        entries[oil_key] = price_text
            
            # 方法2: 如果上面方法没找到，尝试其他选择器
            if not entries:
                oil_elements = doc.select('.oil-price, .price-item, table tr')
                for element in oil_elements:
                    text = element.get_text()
                    # 匹配92#、95#、98#、0#柴油
                    patterns = [
                        (r'92#.*?([\d.]+)元', '92'),
                        (r'95#.*?([\d.]+)元', '95'),
                        (r'98#.*?([\d.]+)元', '98'),
                        (r'0#.*?([\d.]+)元', '0'),
                        (r'柴油.*?([\d.]+)元', '0')
                    ]
                    
                    for pattern, oil_key in patterns:
                        match = re.search(pattern, text)
                        if match and oil_key not in entries:
                            entries[oil_key] = match.group(1) + '元'
            
            # 解析调整信息
            adjustment_info = self.parse_adjustment_info(html, doc)
            
            # 确保所有油品类型都有值
            prices = {
                '92': entries.get('92', '--'),
                '95': entries.get('95', '--'),
                '98': entries.get('98', '--'),
                '0': entries.get('0', '--')
            }
            
            # 检查是否获取到有效数据
            valid_prices = any(price != '--' for price in prices.values())
            if not valid_prices:
                return self._create_error_data(province_name, province_code, "未解析到油价数据")
            
            return {
                "status": "success",
                "name": province_name,
                "code": province_code,
                "prices": prices,
                "unit": "元/升",
                "update_time": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                "next_adjustment": adjustment_info.get('next_adjustment'),
                "trend": adjustment_info.get('trend')
            }
            
        except requests.exceptions.Timeout:
            return self._create_error_data(province_name, province_code, "请求超时")
        except requests.exceptions.RequestException as e:
            return self._create_error_data(province_name, province_code, f"网络请求失败: {str(e)}")
        except Exception as e:
            return self._create_error_data(province_name, province_code, f"解析异常: {str(e)}")
    
    def parse_adjustment_info(self, html, doc):
        """解析油价调整信息"""
        try:
            trend = {
                "direction": "stable",
                "amount": 0,
                "description": "价格稳定"
            }
            
            # 方法1: 从 #youjiaCont 解析
            adjustment_text = ""
            youjia_cont = doc.select_one('#youjiaCont')
            if youjia_cont:
                # 获取第二个div
                divs = youjia_cont.select('div')
                if len(divs) >= 2:
                    adjustment_text = divs[1].get_text().strip()
            
            # 方法2: 从整个HTML解析
            if not adjustment_text:
                adjustment_match = re.search(r'下次油价.*?(\d+月\d+日\d+时调整)', html)
                if adjustment_match:
                    adjustment_text = adjustment_match.group(0)
            
            # 解析调整时间
            next_adjustment = None
            time_match = re.search(r'下次油价(\d+月\d+日\d+时调整)', adjustment_text)
            if time_match:
                next_adjustment = time_match.group(0)
            
            # 解析趋势信息
            trend_match = re.search(r'预计(上调|下调)\s*([\d.]+)元', adjustment_text)
            if not trend_match:
                # 尝试其他模式
                trend_match = re.search(r'预计(涨|跌)\s*([\d.]+)元', adjustment_text)
                if trend_match:
                    direction_map = {'涨': 'up', '跌': 'down'}
                    trend_match = (direction_map.get(trend_match.group(1), 'stable'), trend_match.group(2))
            
            if trend_match and len(trend_match.groups()) >= 2:
                direction = "up" if trend_match.group(1) in ["上调", "涨"] else "down"
                amount = float(trend_match.group(2))
                trend_desc = "上调" if direction == "up" else "下调"
                trend = {
                    "direction": direction,
                    "amount": amount,
                    "description": f"预计{trend_desc}{amount}元/升"
                }
            
            return {
                "next_adjustment": next_adjustment,
                "trend": trend
            }
            
        except Exception as e:
            print(f"解析调整信息异常: {str(e)}")
            return {
                "next_adjustment": None,
                "trend": {
                    "direction": "stable", 
                    "amount": 0,
                    "description": "价格稳定"
                }
            }
    
    def _create_error_data(self, province_name, province_code, error_message):
        """创建错误数据"""
        return {
            "status": "error",
            "name": province_name,
            "code": province_code,
            "error": {
                "code": "FETCH_FAILED",
                "message": error_message,
                "retry_after": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
            },
            "update_time": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
        }
    
    def _create_final_output(self, all_data, success_count):
        """创建最终输出"""
        total_provinces = len(self.provinces)
        status = "success" if success_count > 0 else "error"
        if 0 < success_count < total_provinces:
            status = "partial_success"
        
        return {
            "status": status,
            "last_updated": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            "data_source": "www.qiyoujiage.com",
            "version": "1.0",
            "statistics": {
                "total_provinces": total_provinces,
                "success_count": success_count,
                "error_count": total_provinces - success_count,
                "success_rate": round(success_count / total_provinces * 100, 2)
            },
            "data": all_data
        }

def main():
    """主函数"""
    print("🚀 开始抓取中国各省油价数据...")
    print(f"📋 总共 {len(ChinaOilPriceAPI().provinces)} 个省份")
    
    api = ChinaOilPriceAPI()
    result = api.fetch_all_prices()
    
    # 保存数据
    with open('oil_prices.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 数据抓取完成！")
    print(f"📊 成功: {result['statistics']['success_count']}/{result['statistics']['total_provinces']}")
    print(f"📈 成功率: {result['statistics']['success_rate']}%")
    print(f"💾 数据已保存至: oil_prices.json")
    
    # 显示前几个省份的数据样例
    print("\n📋 数据样例:")
    success_provinces = [name for name, data in result['data'].items() if data['status'] == 'success']
    for province in success_provinces[:3]:
        data = result['data'][province]
        print(f"  {province}: 92#{data['prices']['92']}, 95#{data['prices']['95']}, 98#{data['prices']['98']}, 0#{data['prices']['0']}")

if __name__ == '__main__':
    main()