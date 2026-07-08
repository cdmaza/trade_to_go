SELECT b.timedate, b.buy_price, s.timedate, s.sell_price
FROM (SELECT timedate, buy_price FROM bursaGold ORDER BY buy_price ASC LIMIT 1) b,
     (SELECT timedate, sell_price FROM bursaGold ORDER BY sell_price DESC LIMIT 1) s;
