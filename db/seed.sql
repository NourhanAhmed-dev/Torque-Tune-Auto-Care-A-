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
(2,'Mercedes','C200',2019,'EEE555','VIN000003'),
(2,'Volvo','XC60',2021,'FFF666','VIN000004'),  
(3,'Toyota','Hilux',2020,'GGG777','VIN000005');

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


-- proplem 1
-- Presets (build types) — the picker/menu the user chooses from
DELETE FROM build_presets;
INSERT INTO build_presets (preset_key, display_name) VALUES
    ('stage1_ecu_only',              'Stage 1 — ECU Tune Only'),
    ('stage2_turbo_stock_power',     'Stage 2 Turbo — Stock Power Target (<=320 whp)'),
    ('stage2_turbo_high_power',      'Stage 2 Turbo — High Power Target (>320 whp)'),
    ('stage2_turbo_boost_controller','Stage 2 Turbo — With Electronic Boost Controller'),
    ('stage2_turbo_full_send',       'Stage 2 Turbo — Full Send (high power + boost controller)'),
    ('stage3_race_build',            'Stage 3 — Race Build (race-spec suppliers)'),
    ('intercooler_upgrade_only',     'Intercooler Upgrade Only'),
    ('exhaust_upgrade_only',         'Exhaust / Downpipe Upgrade Only');

-- Seed: parts required per preset 
-- Stage 1: software-only tune, no hardware
INSERT INTO build_part_requirements (preset_key, part_id, part_name, supplier, price, quantity) VALUES
    ('stage1_ecu_only', 103, 'Stage 2 ECU Tune', 'SupplierB', 900.00, 1);
 
-- Stage 2, stock power target: turbo + downpipe + intercooler + tune,
-- no injectors needed (tune stays under 320 whp)
INSERT INTO build_part_requirements (preset_key, part_id, part_name, supplier, price, quantity) VALUES
    ('stage2_turbo_stock_power', 101, 'Stage 2 Turbocharger Kit',   'SupplierA', 1800.00, 1),
    ('stage2_turbo_stock_power', 104, '3-Inch High-Flow Downpipe',  'SupplierA',  550.00, 1),
    ('stage2_turbo_stock_power', 102, 'Front-Mount Intercooler Kit','SupplierA',  650.00, 1),
    ('stage2_turbo_stock_power', 103, 'Stage 2 ECU Tune',           'SupplierB',  900.00, 1);
 
-- Stage 2, high power target: same as above + injectors (target > 320 whp)
INSERT INTO build_part_requirements (preset_key, part_id, part_name, supplier, price, quantity) VALUES
    ('stage2_turbo_high_power', 101, 'Stage 2 Turbocharger Kit',        'SupplierA', 1800.00, 1),
    ('stage2_turbo_high_power', 104, '3-Inch High-Flow Downpipe',       'SupplierA',  550.00, 1),
    ('stage2_turbo_high_power', 102, 'Front-Mount Intercooler Kit',     'SupplierA',  650.00, 1),
    ('stage2_turbo_high_power', 103, 'Stage 2 ECU Tune',                'SupplierB',  900.00, 1),
    ('stage2_turbo_high_power', 105, '1000cc Fuel Injectors (Set of 4)','SupplierB',  450.00, 1);
 
-- Stage 2, with boost controller: base build + electronic boost controller
INSERT INTO build_part_requirements (preset_key, part_id, part_name, supplier, price, quantity) VALUES
    ('stage2_turbo_boost_controller', 101, 'Stage 2 Turbocharger Kit',    'SupplierA', 1800.00, 1),
    ('stage2_turbo_boost_controller', 104, '3-Inch High-Flow Downpipe',   'SupplierA',  550.00, 1),
    ('stage2_turbo_boost_controller', 102, 'Front-Mount Intercooler Kit', 'SupplierA',  650.00, 1),
    ('stage2_turbo_boost_controller', 103, 'Stage 2 ECU Tune',            'SupplierB',  900.00, 1),
    ('stage2_turbo_boost_controller', 106, 'Electronic Boost Controller', 'SupplierB',  300.00, 1);
 
-- Stage 2, full send: everything — high power + boost controller
INSERT INTO build_part_requirements (preset_key, part_id, part_name, supplier, price, quantity) VALUES
    ('stage2_turbo_full_send', 101, 'Stage 2 Turbocharger Kit',        'SupplierA', 1800.00, 1),
    ('stage2_turbo_full_send', 104, '3-Inch High-Flow Downpipe',       'SupplierA',  550.00, 1),
    ('stage2_turbo_full_send', 102, 'Front-Mount Intercooler Kit',     'SupplierA',  650.00, 1),
    ('stage2_turbo_full_send', 103, 'Stage 2 ECU Tune',                'SupplierB',  900.00, 1),
    ('stage2_turbo_full_send', 105, '1000cc Fuel Injectors (Set of 4)','SupplierB',  450.00, 1),
    ('stage2_turbo_full_send', 106, 'Electronic Boost Controller',     'SupplierB',  300.00, 1);
 
-- Stage 3 race build: same physical parts, sourced from race-spec
INSERT INTO build_part_requirements (preset_key, part_id, part_name, supplier, price, quantity) VALUES
    ('stage3_race_build', 101, 'Stage 2 Turbocharger Kit',        'SupplierC', 2200.00, 1),
    ('stage3_race_build', 104, '3-Inch High-Flow Downpipe',       'SupplierC',  650.00, 1),
    ('stage3_race_build', 102, 'Front-Mount Intercooler Kit',     'SupplierC',  800.00, 1),
    ('stage3_race_build', 103, 'Stage 2 ECU Tune',                'SupplierB',  900.00, 1),
    ('stage3_race_build', 105, '1000cc Fuel Injectors (Set of 4)','SupplierB',  450.00, 1),
    ('stage3_race_build', 106, 'Electronic Boost Controller',     'SupplierB',  300.00, 1);
 
-- Standalone single-part presets — a customer who only wants one upgrade
INSERT INTO build_part_requirements (preset_key, part_id, part_name, supplier, price, quantity) VALUES
    ('intercooler_upgrade_only', 102, 'Front-Mount Intercooler Kit', 'SupplierA', 650.00, 1);
 
INSERT INTO build_part_requirements (preset_key, part_id, part_name, supplier, price, quantity) VALUES
    ('exhaust_upgrade_only', 104, '3-Inch High-Flow Downpipe', 'SupplierA', 550.00, 1);

-- Seed tow providers(graph 3)
INSERT OR IGNORE INTO tow_providers (provider_id, name, latitude, longitude, status) VALUES
    ('PROV-001', 'Alex Rapid Tow',    31.2001, 29.9187, 'available'),
    ('PROV-002', 'Giza Recovery Co.', 30.0131, 31.2089, 'available'),
    ('PROV-003', 'Nile Fleet Assist', 30.0444, 31.2357, 'available'),
    ('PROV-004', 'Delta Roadside',    31.2156, 29.9553, 'available'),
    ('PROV-005', 'Cairo 24/7 Tow',    30.0626, 31.2497, 'available');

INSERT OR IGNORE INTO vehicle_telematics
(vehicle_id, battery_voltage, engine_temperature, latitude, longitude, dtc_codes) VALUES
(1, 12.4, 118, 30.0444, 31.2357, '["P0217"]'),
(2, 12.6, 90,  31.2001, 29.9187, '["P0420"]'),
(3, 11.9, 95,  30.0131, 31.2089, '[]');
--for graph 2--
INSERT INTO episodic_memories (memory_id, content, importance, reason, vehicle_id, client_id) VALUES
('mem_v1_001', 'ECU Stage 1 tune performed. Boost target raised to 1.1 bar. No anomalies. Customer satisfied on pickup.', 3, 'original tune record', 1, 1),
('mem_v1_002', 'Customer returned 1 week later reporting minor hesitation at low RPM. Diagnosed as spark plug gap issue, resolved on-site.', 2, 'early symptom', 1, 1),
('mem_v3_001', 'Catalytic converter delete performed. Customer warned about potential emissions test failure. Signed waiver.', 3, 'warranty-relevant modification', 3, 2);