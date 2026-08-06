INSERT INTO clients(full_name, phone, email, address) VALUES
('Ahmed Ali','01011111111','ahmed@gmail.com','Alexandria'),
('Mohamed Samir','01022222222','mohamed@gmail.com','Cairo'),
('Youssef Adel','01033333333','youssef@gmail.com','Giza');

INSERT INTO technicians(full_name, tech_phone, specialization) VALUES
('Omar Hassan','01099998888','ECU Tuning'),
('Mahmoud Salem','01077776666','Performance');

INSERT INTO vehicles(client_id, make, model, year, license_plate, vin) VALUES
(1,'BMW','320i',2021,'ABC123','VIN000001'),
(1,'Audi','A4',2020,'XYZ456','VIN000002'),
(2,'Mercedes','C200',2019,'EEE555','VIN000003');

INSERT INTO appointments(appointment_date, vehicle_id, tech_id) VALUES
('2026-08-10 10:00',1,1),
('2026-08-11 12:30',2,1),
('2026-08-12 09:00',3,2);

INSERT INTO tuning_logs(status, category, description, vehicle_id, tech_id) VALUES
('complete','performance','ECU Stage 1 Tune',1,1),
('complete','cosmetic','Black alloy wheels',2,1),
('awaiting_signoff','emissions_affecting','Catalytic converter delete',3,2);

INSERT INTO parts_catalog(log_id, part_name, quantity, price) VALUES
(1,'Performance Air Filter',1,1200),
(1,'ECU License',1,3500),
(2,'19 inch Alloy Wheels',4,8000),
(3,'Straight Pipe',1,2000);

INSERT INTO invoices(total_amount, payment, client_id) VALUES
(9500,'paid',1),
(8000,'partial',1),
(2000,'unpaid',2);