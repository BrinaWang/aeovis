PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE evaluation_runs (
    run_id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    engine TEXT NOT NULL,
    model TEXT NOT NULL,
    num_prompts INTEGER NOT NULL,
    filters TEXT,  -- JSON: {topic, persona, priority}
    status TEXT,   -- "completed", "partial_failure", "failed"
    cost REAL NOT NULL DEFAULT 0.0,
    duration_seconds INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO evaluation_runs VALUES('b3b61b27-e79b-4a87-833b-84c4de188e99','2026-08-17 19:35:50','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:35:50');
INSERT INTO evaluation_runs VALUES('e72e6a50-6648-40a1-95b6-1fa877b4d930','2026-08-17 19:35:50','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:35:50');
INSERT INTO evaluation_runs VALUES('ec4f2e64-3463-4d58-ad7d-575402c4896f','2026-08-17 19:35:50','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:35:50');
INSERT INTO evaluation_runs VALUES('4046c32d-69db-4f12-bf5e-456ed96e9048','2026-08-17 19:35:50','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:35:50');
INSERT INTO evaluation_runs VALUES('c3eb55b0-a943-4db5-970c-e7be6373701a','2026-08-17 19:35:55','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:35:55');
INSERT INTO evaluation_runs VALUES('ee027238-507e-470b-8644-ba85936aec7d','2026-08-17 19:48:24','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:48:24');
INSERT INTO evaluation_runs VALUES('b173df0d-64e6-4695-964e-ae141cd44118','2026-08-17 19:48:24','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:48:24');
INSERT INTO evaluation_runs VALUES('6d5127d3-ff39-4caa-875f-bc5d9f9f0fb3','2026-08-17 19:48:24','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:48:24');
INSERT INTO evaluation_runs VALUES('bb4efcd5-6b82-43b1-8ba8-dc596aa2a2c2','2026-08-17 19:48:24','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:48:24');
INSERT INTO evaluation_runs VALUES('6632931b-c58b-4e6b-b948-9439f96fd5dd','2026-08-17 19:48:29','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:48:29');
INSERT INTO evaluation_runs VALUES('66d0b8e4-f8ae-43f5-a173-a962832d8be5','2026-08-17 19:52:37','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:52:37');
INSERT INTO evaluation_runs VALUES('d4853ed2-3f32-4956-b865-25bcc39cd31c','2026-08-17 19:52:37','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:52:37');
INSERT INTO evaluation_runs VALUES('5a02b6b8-81b9-4a80-86fd-230ee2cdabaa','2026-08-17 19:52:37','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:52:37');
INSERT INTO evaluation_runs VALUES('bd878692-9637-460f-b786-43930ac828cc','2026-08-17 19:52:37','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:52:37');
INSERT INTO evaluation_runs VALUES('0d7af985-11b2-43ed-a30a-884afc904350','2026-08-17 19:52:42','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:52:42');
INSERT INTO evaluation_runs VALUES('847db008-e9ce-4c94-90ac-0e56ebdda987','2026-08-17 19:56:44','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:56:44');
INSERT INTO evaluation_runs VALUES('07281bf0-0676-4d6f-bb16-ac5df5aac64c','2026-08-17 19:56:44','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:56:44');
INSERT INTO evaluation_runs VALUES('b2fc0e29-5c9c-4f79-b1e7-f799eb398c5f','2026-08-17 19:56:44','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:56:44');
INSERT INTO evaluation_runs VALUES('a678bcf1-a992-4f63-a434-bf9adaae11f1','2026-08-17 19:56:44','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:56:44');
INSERT INTO evaluation_runs VALUES('30f2daee-b7fe-4f73-8fd5-eaea221af24f','2026-08-17 19:56:49','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 19:56:49');
INSERT INTO evaluation_runs VALUES('76a3f81b-28c6-4170-9e30-7c05a10c5f72','2026-08-17 20:00:03','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:00:03');
INSERT INTO evaluation_runs VALUES('4eb30bc7-57eb-433d-a79b-1962b895ae53','2026-08-17 20:00:03','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:00:03');
INSERT INTO evaluation_runs VALUES('fc411e4d-5387-4774-8417-d2d93f8be43d','2026-08-17 20:00:03','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:00:03');
INSERT INTO evaluation_runs VALUES('0c734e3c-9ac5-4511-99ec-b3039a14bde3','2026-08-17 20:00:03','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:00:03');
INSERT INTO evaluation_runs VALUES('bbf1fb83-719c-4602-b53b-36f05a568b59','2026-08-17 20:00:07','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:00:07');
INSERT INTO evaluation_runs VALUES('c730b1d3-5776-4678-adce-522301fef3d9','2026-08-17 20:09:19','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:09:19');
INSERT INTO evaluation_runs VALUES('065036b0-11fb-45b1-9f27-e18301ea6d4a','2026-08-17 20:09:19','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:09:19');
INSERT INTO evaluation_runs VALUES('fb1cd0e2-f7ef-4afd-a9e2-fd0bbc851626','2026-08-17 20:09:19','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:09:19');
INSERT INTO evaluation_runs VALUES('1f4c4e6e-3a36-44c2-9782-c5dbf2834d37','2026-08-17 20:09:19','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:09:19');
INSERT INTO evaluation_runs VALUES('923a4c8c-a5ac-4ced-9f51-6bd6bf088068','2026-08-17 20:09:24','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:09:24');
INSERT INTO evaluation_runs VALUES('99a49ecd-d14a-45e5-8465-4d9f67bdf97d','2026-08-17 20:10:26','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:10:26');
INSERT INTO evaluation_runs VALUES('5813623c-8710-4174-be76-34e393d7f283','2026-08-17 20:10:26','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:10:26');
INSERT INTO evaluation_runs VALUES('a215a08c-8eb0-44cb-bdaa-c3c5e39d5169','2026-08-17 20:10:26','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:10:26');
INSERT INTO evaluation_runs VALUES('f402abb3-4114-48e8-913f-d34d4f81fbf6','2026-08-17 20:10:26','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:10:26');
INSERT INTO evaluation_runs VALUES('5cab1802-6a7a-4689-9ffa-336ace5cfb8f','2026-08-17 20:10:26','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:10:26');
INSERT INTO evaluation_runs VALUES('b251f521-a681-4262-8929-59beec9f31a2','2026-08-17 20:10:57','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:10:57');
INSERT INTO evaluation_runs VALUES('28d9a7d0-e21a-4ddd-bd80-d0f19be34bec','2026-08-17 20:10:57','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:10:57');
INSERT INTO evaluation_runs VALUES('8fd8d43e-fa43-4003-8c0c-6b433b52a9a7','2026-08-17 20:10:57','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:10:57');
INSERT INTO evaluation_runs VALUES('04f1a4e9-c36d-4b4c-b853-2bf6a6bff896','2026-08-17 20:10:57','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:10:57');
INSERT INTO evaluation_runs VALUES('eab2cd81-e09e-401e-8aee-4b72821e3be0','2026-08-17 20:11:01','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:11:01');
INSERT INTO evaluation_runs VALUES('89431021-daca-4b34-a63b-5715d8d6862d','2026-08-17 20:17:32','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:17:32');
INSERT INTO evaluation_runs VALUES('17751667-1c85-4796-aae0-2fbbe12b6544','2026-08-17 20:17:32','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:17:32');
INSERT INTO evaluation_runs VALUES('555cb385-77a5-4085-9f3e-25e046daef1f','2026-08-17 20:17:32','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:17:32');
INSERT INTO evaluation_runs VALUES('bb27e977-ac2c-4e58-a214-8cd4287fc0cd','2026-08-17 20:17:32','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:17:32');
INSERT INTO evaluation_runs VALUES('80021247-50b5-4d6e-a7ac-8f4ddb07acf4','2026-08-17 20:17:37','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:17:37');
INSERT INTO evaluation_runs VALUES('e222969b-f30a-496d-b4a3-97fc967961d6','2026-08-17 20:23:57','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:23:57');
INSERT INTO evaluation_runs VALUES('be31e8dc-a9e7-42c5-95d4-0d8b32fca818','2026-08-17 20:23:57','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:23:57');
INSERT INTO evaluation_runs VALUES('7bda8f98-b65c-43ef-82c3-a1f43a1b03c6','2026-08-17 20:23:57','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:23:57');
INSERT INTO evaluation_runs VALUES('63da4d30-eb35-4b37-951e-9130365eb9c2','2026-08-17 20:23:57','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:23:57');
INSERT INTO evaluation_runs VALUES('8e757160-228d-436f-b720-ee1197a9fd0b','2026-08-17 20:24:01','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:24:01');
INSERT INTO evaluation_runs VALUES('1f127461-a747-40d7-857d-a52e79f24df7','2026-08-17 20:26:39','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:26:39');
INSERT INTO evaluation_runs VALUES('2650830b-0e3b-4b65-b02e-52c7e282558b','2026-08-17 20:26:39','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:26:39');
INSERT INTO evaluation_runs VALUES('adb2a390-5e87-4735-8ca3-1ce35666d7c3','2026-08-17 20:26:39','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:26:39');
INSERT INTO evaluation_runs VALUES('f96c09a9-37f0-4eaa-8903-4553cf305e16','2026-08-17 20:26:39','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:26:39');
INSERT INTO evaluation_runs VALUES('21fa3f36-476e-43d0-899f-292b53ead826','2026-08-17 20:26:44','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:26:44');
INSERT INTO evaluation_runs VALUES('769bf93c-f32a-4590-9f37-72c575801228','2026-08-17 20:29:26','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:29:26');
INSERT INTO evaluation_runs VALUES('56fb649e-85e2-4185-909e-d48a6a1cc185','2026-08-17 20:29:26','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:29:26');
INSERT INTO evaluation_runs VALUES('cab034f5-3606-455b-a106-91052a1b3dec','2026-08-17 20:29:26','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:29:26');
INSERT INTO evaluation_runs VALUES('4cf80491-d1b5-4338-bd72-1bfec765c6f9','2026-08-17 20:29:26','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:29:26');
INSERT INTO evaluation_runs VALUES('e9b042d3-c80f-4e60-b4c7-20d7cf86ab4e','2026-08-17 20:29:31','mock','mock-v1',1,NULL,'success',0.0,0,'2026-08-17 20:29:31');
CREATE TABLE raw_responses (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    prompt_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    response_text TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost REAL DEFAULT 0.0,
    latency_ms INTEGER,
    status TEXT,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES evaluation_runs(run_id)
);
INSERT INTO raw_responses VALUES('mock-05911aea601e','b3b61b27-e79b-4a87-833b-84c4de188e99','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:35:50');
INSERT INTO raw_responses VALUES('mock-d0613fa95f86','e72e6a50-6648-40a1-95b6-1fa877b4d930','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:35:50');
INSERT INTO raw_responses VALUES('mock-f9d616d382cc','e72e6a50-6648-40a1-95b6-1fa877b4d930','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:35:50');
INSERT INTO raw_responses VALUES('mock-0697976efac3','e72e6a50-6648-40a1-95b6-1fa877b4d930','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:35:50');
INSERT INTO raw_responses VALUES('mock-d34d42f64bc1','ec4f2e64-3463-4d58-ad7d-575402c4896f','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:35:50');
INSERT INTO raw_responses VALUES('mock-7405986285fe','4046c32d-69db-4f12-bf5e-456ed96e9048','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:35:50');
INSERT INTO raw_responses VALUES('mock-3c954ae9ea27','c3eb55b0-a943-4db5-970c-e7be6373701a','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:35:55');
INSERT INTO raw_responses VALUES('mock-32df3aaf0e52','ee027238-507e-470b-8644-ba85936aec7d','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:48:24');
INSERT INTO raw_responses VALUES('mock-eea3150fe704','b173df0d-64e6-4695-964e-ae141cd44118','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:48:24');
INSERT INTO raw_responses VALUES('mock-52d7e16476ba','b173df0d-64e6-4695-964e-ae141cd44118','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:48:24');
INSERT INTO raw_responses VALUES('mock-4a4c2fcaf787','b173df0d-64e6-4695-964e-ae141cd44118','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:48:24');
INSERT INTO raw_responses VALUES('mock-3a3c79615b46','6d5127d3-ff39-4caa-875f-bc5d9f9f0fb3','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:48:24');
INSERT INTO raw_responses VALUES('mock-0d92cbfef298','bb4efcd5-6b82-43b1-8ba8-dc596aa2a2c2','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:48:24');
INSERT INTO raw_responses VALUES('mock-5072a17ba59e','6632931b-c58b-4e6b-b948-9439f96fd5dd','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:48:29');
INSERT INTO raw_responses VALUES('mock-df127bf9599b','66d0b8e4-f8ae-43f5-a173-a962832d8be5','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:52:37');
INSERT INTO raw_responses VALUES('mock-e0d3ced1b179','d4853ed2-3f32-4956-b865-25bcc39cd31c','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:52:37');
INSERT INTO raw_responses VALUES('mock-2932edc17a8b','d4853ed2-3f32-4956-b865-25bcc39cd31c','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:52:37');
INSERT INTO raw_responses VALUES('mock-59467a7200a9','d4853ed2-3f32-4956-b865-25bcc39cd31c','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:52:37');
INSERT INTO raw_responses VALUES('mock-b421aee29a9e','5a02b6b8-81b9-4a80-86fd-230ee2cdabaa','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:52:37');
INSERT INTO raw_responses VALUES('mock-d2c54eb44205','bd878692-9637-460f-b786-43930ac828cc','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:52:37');
INSERT INTO raw_responses VALUES('mock-07016134dc0e','0d7af985-11b2-43ed-a30a-884afc904350','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:52:42');
INSERT INTO raw_responses VALUES('mock-2450263c9cf3','847db008-e9ce-4c94-90ac-0e56ebdda987','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:56:44');
INSERT INTO raw_responses VALUES('mock-030c4a866f71','07281bf0-0676-4d6f-bb16-ac5df5aac64c','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:56:44');
INSERT INTO raw_responses VALUES('mock-af16ed724d54','07281bf0-0676-4d6f-bb16-ac5df5aac64c','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:56:44');
INSERT INTO raw_responses VALUES('mock-0a8f144cc730','07281bf0-0676-4d6f-bb16-ac5df5aac64c','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:56:44');
INSERT INTO raw_responses VALUES('mock-7960e06e5f7c','b2fc0e29-5c9c-4f79-b1e7-f799eb398c5f','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:56:44');
INSERT INTO raw_responses VALUES('mock-d5a087b348ff','a678bcf1-a992-4f63-a434-bf9adaae11f1','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:56:44');
INSERT INTO raw_responses VALUES('mock-17541a94efaf','30f2daee-b7fe-4f73-8fd5-eaea221af24f','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 19:56:49');
INSERT INTO raw_responses VALUES('mock-3472b3788ec2','76a3f81b-28c6-4170-9e30-7c05a10c5f72','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:00:03');
INSERT INTO raw_responses VALUES('mock-00782c4bbd2d','4eb30bc7-57eb-433d-a79b-1962b895ae53','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:00:03');
INSERT INTO raw_responses VALUES('mock-8036fcc0ec5b','4eb30bc7-57eb-433d-a79b-1962b895ae53','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:00:03');
INSERT INTO raw_responses VALUES('mock-b4388bba239a','4eb30bc7-57eb-433d-a79b-1962b895ae53','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:00:03');
INSERT INTO raw_responses VALUES('mock-811238f09bc7','fc411e4d-5387-4774-8417-d2d93f8be43d','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:00:03');
INSERT INTO raw_responses VALUES('mock-769b1d7f18a8','0c734e3c-9ac5-4511-99ec-b3039a14bde3','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:00:03');
INSERT INTO raw_responses VALUES('mock-073491925d4a','bbf1fb83-719c-4602-b53b-36f05a568b59','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:00:07');
INSERT INTO raw_responses VALUES('mock-2a3be5942966','c730b1d3-5776-4678-adce-522301fef3d9','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:09:19');
INSERT INTO raw_responses VALUES('mock-00c9cd7619d2','065036b0-11fb-45b1-9f27-e18301ea6d4a','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:09:19');
INSERT INTO raw_responses VALUES('mock-52ec605b1a82','065036b0-11fb-45b1-9f27-e18301ea6d4a','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:09:19');
INSERT INTO raw_responses VALUES('mock-f16cdf246666','065036b0-11fb-45b1-9f27-e18301ea6d4a','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:09:19');
INSERT INTO raw_responses VALUES('mock-77655dba49d0','fb1cd0e2-f7ef-4afd-a9e2-fd0bbc851626','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:09:19');
INSERT INTO raw_responses VALUES('mock-62c24a1205a1','1f4c4e6e-3a36-44c2-9782-c5dbf2834d37','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:09:19');
INSERT INTO raw_responses VALUES('mock-621e4599a861','923a4c8c-a5ac-4ced-9f51-6bd6bf088068','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:09:24');
INSERT INTO raw_responses VALUES('mock-2c481b605020','99a49ecd-d14a-45e5-8465-4d9f67bdf97d','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:26');
INSERT INTO raw_responses VALUES('mock-67ddd8d65294','5813623c-8710-4174-be76-34e393d7f283','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:26');
INSERT INTO raw_responses VALUES('mock-c15b0e5b5057','a215a08c-8eb0-44cb-bdaa-c3c5e39d5169','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:26');
INSERT INTO raw_responses VALUES('mock-269274be7442','a215a08c-8eb0-44cb-bdaa-c3c5e39d5169','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:26');
INSERT INTO raw_responses VALUES('mock-fb5d59e45473','a215a08c-8eb0-44cb-bdaa-c3c5e39d5169','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:26');
INSERT INTO raw_responses VALUES('mock-bdf6d2697d75','f402abb3-4114-48e8-913f-d34d4f81fbf6','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:26');
INSERT INTO raw_responses VALUES('mock-3c06a7085f0f','5cab1802-6a7a-4689-9ffa-336ace5cfb8f','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:26');
INSERT INTO raw_responses VALUES('mock-18553edf8e5d','b251f521-a681-4262-8929-59beec9f31a2','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:57');
INSERT INTO raw_responses VALUES('mock-03824e2b406b','28d9a7d0-e21a-4ddd-bd80-d0f19be34bec','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:57');
INSERT INTO raw_responses VALUES('mock-d35cf01b2348','28d9a7d0-e21a-4ddd-bd80-d0f19be34bec','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:57');
INSERT INTO raw_responses VALUES('mock-41a5cd9e507c','28d9a7d0-e21a-4ddd-bd80-d0f19be34bec','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:57');
INSERT INTO raw_responses VALUES('mock-aa6a39371a3b','8fd8d43e-fa43-4003-8c0c-6b433b52a9a7','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:57');
INSERT INTO raw_responses VALUES('mock-fa848ab698c0','04f1a4e9-c36d-4b4c-b853-2bf6a6bff896','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:10:57');
INSERT INTO raw_responses VALUES('mock-e1c8ef7926d0','eab2cd81-e09e-401e-8aee-4b72821e3be0','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:11:01');
INSERT INTO raw_responses VALUES('mock-2d8fd315cf9c','89431021-daca-4b34-a63b-5715d8d6862d','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:17:32');
INSERT INTO raw_responses VALUES('mock-eb80c644f28f','17751667-1c85-4796-aae0-2fbbe12b6544','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:17:32');
INSERT INTO raw_responses VALUES('mock-eadb67712881','17751667-1c85-4796-aae0-2fbbe12b6544','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:17:32');
INSERT INTO raw_responses VALUES('mock-4a0dbbbfb17f','17751667-1c85-4796-aae0-2fbbe12b6544','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:17:32');
INSERT INTO raw_responses VALUES('mock-188341555fe8','555cb385-77a5-4085-9f3e-25e046daef1f','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:17:32');
INSERT INTO raw_responses VALUES('mock-9ba9591ff128','bb27e977-ac2c-4e58-a214-8cd4287fc0cd','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:17:32');
INSERT INTO raw_responses VALUES('mock-1fff03e9eaa4','80021247-50b5-4d6e-a7ac-8f4ddb07acf4','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:17:37');
INSERT INTO raw_responses VALUES('mock-a14490649e22','e222969b-f30a-496d-b4a3-97fc967961d6','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:23:57');
INSERT INTO raw_responses VALUES('mock-cf7f8ee9261e','be31e8dc-a9e7-42c5-95d4-0d8b32fca818','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:23:57');
INSERT INTO raw_responses VALUES('mock-c0d8353d16d7','be31e8dc-a9e7-42c5-95d4-0d8b32fca818','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:23:57');
INSERT INTO raw_responses VALUES('mock-a10bff4ea55f','be31e8dc-a9e7-42c5-95d4-0d8b32fca818','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:23:57');
INSERT INTO raw_responses VALUES('mock-2c334556ca4e','7bda8f98-b65c-43ef-82c3-a1f43a1b03c6','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:23:57');
INSERT INTO raw_responses VALUES('mock-a4b8fd194742','63da4d30-eb35-4b37-951e-9130365eb9c2','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:23:57');
INSERT INTO raw_responses VALUES('mock-6792daf2a5f9','8e757160-228d-436f-b720-ee1197a9fd0b','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:24:01');
INSERT INTO raw_responses VALUES('mock-8ae78cee18bb','1f127461-a747-40d7-857d-a52e79f24df7','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:26:39');
INSERT INTO raw_responses VALUES('mock-86be3e6fb794','2650830b-0e3b-4b65-b02e-52c7e282558b','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:26:39');
INSERT INTO raw_responses VALUES('mock-e558dd9b5011','2650830b-0e3b-4b65-b02e-52c7e282558b','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:26:39');
INSERT INTO raw_responses VALUES('mock-c58f106cea24','2650830b-0e3b-4b65-b02e-52c7e282558b','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:26:39');
INSERT INTO raw_responses VALUES('mock-9b00412a3116','adb2a390-5e87-4735-8ca3-1ce35666d7c3','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:26:39');
INSERT INTO raw_responses VALUES('mock-4d213c603a74','f96c09a9-37f0-4eaa-8903-4553cf305e16','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:26:39');
INSERT INTO raw_responses VALUES('mock-7c3964419ee7','21fa3f36-476e-43d0-899f-292b53ead826','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:26:44');
INSERT INTO raw_responses VALUES('mock-54b5dba2d234','769bf93c-f32a-4590-9f37-72c575801228','test-1','mock','Mock answer for prompt: What is 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:29:26');
INSERT INTO raw_responses VALUES('mock-2a72025bc8cc','56fb649e-85e2-4185-909e-d48a6a1cc185','test-0','mock','Mock answer for prompt: Question 0?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:29:26');
INSERT INTO raw_responses VALUES('mock-f5cb629b6b3f','56fb649e-85e2-4185-909e-d48a6a1cc185','test-1','mock','Mock answer for prompt: Question 1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:29:26');
INSERT INTO raw_responses VALUES('mock-be7b4b05e065','56fb649e-85e2-4185-909e-d48a6a1cc185','test-2','mock','Mock answer for prompt: Question 2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:29:26');
INSERT INTO raw_responses VALUES('mock-038603e18b96','cab034f5-3606-455b-a106-91052a1b3dec','math-1','mock','Mock answer for prompt: 2+2?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:29:26');
INSERT INTO raw_responses VALUES('mock-22065b5c0ea7','4cf80491-d1b5-4338-bd72-1bfec765c6f9','test-1','mock','Mock answer for prompt: Q1?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:29:26');
INSERT INTO raw_responses VALUES('mock-6753a996f787','e9b042d3-c80f-4e60-b4c7-20d7cf86ab4e','demo-1','mock','Mock answer for prompt: Best Oracle CDC tools?',NULL,NULL,NULL,150,'success',NULL,'2026-08-17 20:29:31');
CREATE TABLE response_analysis (
    id TEXT PRIMARY KEY,
    raw_response_id TEXT NOT NULL,
    striim_mentioned INTEGER,
    striim_recommended INTEGER,
    striim_position INTEGER,
    brands_found TEXT,        -- JSON: [{name, position, is_recommended}, ...]
    claims TEXT,              -- JSON: [{text, sentiment, confidence, supporting_citation}, ...]
    citations TEXT,           -- JSON: ["https://...", ...]
    extraction_confidence REAL,
    flagged_for_review INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (raw_response_id) REFERENCES raw_responses(id)
);
INSERT INTO response_analysis VALUES('analysis-mock-05911aea601e','mock-05911aea601e',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:35:50');
INSERT INTO response_analysis VALUES('analysis-mock-d0613fa95f86','mock-d0613fa95f86',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:35:50');
INSERT INTO response_analysis VALUES('analysis-mock-f9d616d382cc','mock-f9d616d382cc',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:35:50');
INSERT INTO response_analysis VALUES('analysis-mock-0697976efac3','mock-0697976efac3',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:35:50');
INSERT INTO response_analysis VALUES('analysis-mock-d34d42f64bc1','mock-d34d42f64bc1',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:35:50');
INSERT INTO response_analysis VALUES('analysis-mock-7405986285fe','mock-7405986285fe',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:35:50');
INSERT INTO response_analysis VALUES('analysis-mock-3c954ae9ea27','mock-3c954ae9ea27',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:35:55');
INSERT INTO response_analysis VALUES('analysis-mock-32df3aaf0e52','mock-32df3aaf0e52',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:48:24');
INSERT INTO response_analysis VALUES('analysis-mock-eea3150fe704','mock-eea3150fe704',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:48:24');
INSERT INTO response_analysis VALUES('analysis-mock-52d7e16476ba','mock-52d7e16476ba',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:48:24');
INSERT INTO response_analysis VALUES('analysis-mock-4a4c2fcaf787','mock-4a4c2fcaf787',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:48:24');
INSERT INTO response_analysis VALUES('analysis-mock-3a3c79615b46','mock-3a3c79615b46',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:48:24');
INSERT INTO response_analysis VALUES('analysis-mock-0d92cbfef298','mock-0d92cbfef298',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:48:24');
INSERT INTO response_analysis VALUES('analysis-mock-5072a17ba59e','mock-5072a17ba59e',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:48:29');
INSERT INTO response_analysis VALUES('analysis-mock-df127bf9599b','mock-df127bf9599b',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:52:37');
INSERT INTO response_analysis VALUES('analysis-mock-e0d3ced1b179','mock-e0d3ced1b179',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:52:37');
INSERT INTO response_analysis VALUES('analysis-mock-2932edc17a8b','mock-2932edc17a8b',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:52:37');
INSERT INTO response_analysis VALUES('analysis-mock-59467a7200a9','mock-59467a7200a9',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:52:37');
INSERT INTO response_analysis VALUES('analysis-mock-b421aee29a9e','mock-b421aee29a9e',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:52:37');
INSERT INTO response_analysis VALUES('analysis-mock-d2c54eb44205','mock-d2c54eb44205',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:52:37');
INSERT INTO response_analysis VALUES('analysis-mock-07016134dc0e','mock-07016134dc0e',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:52:42');
INSERT INTO response_analysis VALUES('analysis-mock-2450263c9cf3','mock-2450263c9cf3',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:56:44');
INSERT INTO response_analysis VALUES('analysis-mock-030c4a866f71','mock-030c4a866f71',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:56:44');
INSERT INTO response_analysis VALUES('analysis-mock-af16ed724d54','mock-af16ed724d54',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:56:44');
INSERT INTO response_analysis VALUES('analysis-mock-0a8f144cc730','mock-0a8f144cc730',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:56:44');
INSERT INTO response_analysis VALUES('analysis-mock-7960e06e5f7c','mock-7960e06e5f7c',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:56:44');
INSERT INTO response_analysis VALUES('analysis-mock-d5a087b348ff','mock-d5a087b348ff',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:56:44');
INSERT INTO response_analysis VALUES('analysis-mock-17541a94efaf','mock-17541a94efaf',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 19:56:49');
INSERT INTO response_analysis VALUES('analysis-mock-3472b3788ec2','mock-3472b3788ec2',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:00:03');
INSERT INTO response_analysis VALUES('analysis-mock-00782c4bbd2d','mock-00782c4bbd2d',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:00:03');
INSERT INTO response_analysis VALUES('analysis-mock-8036fcc0ec5b','mock-8036fcc0ec5b',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:00:03');
INSERT INTO response_analysis VALUES('analysis-mock-b4388bba239a','mock-b4388bba239a',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:00:03');
INSERT INTO response_analysis VALUES('analysis-mock-811238f09bc7','mock-811238f09bc7',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:00:03');
INSERT INTO response_analysis VALUES('analysis-mock-769b1d7f18a8','mock-769b1d7f18a8',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:00:03');
INSERT INTO response_analysis VALUES('analysis-mock-073491925d4a','mock-073491925d4a',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:00:07');
INSERT INTO response_analysis VALUES('analysis-mock-2a3be5942966','mock-2a3be5942966',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:09:19');
INSERT INTO response_analysis VALUES('analysis-mock-00c9cd7619d2','mock-00c9cd7619d2',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:09:19');
INSERT INTO response_analysis VALUES('analysis-mock-52ec605b1a82','mock-52ec605b1a82',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:09:19');
INSERT INTO response_analysis VALUES('analysis-mock-f16cdf246666','mock-f16cdf246666',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:09:19');
INSERT INTO response_analysis VALUES('analysis-mock-77655dba49d0','mock-77655dba49d0',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:09:19');
INSERT INTO response_analysis VALUES('analysis-mock-62c24a1205a1','mock-62c24a1205a1',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:09:19');
INSERT INTO response_analysis VALUES('analysis-mock-621e4599a861','mock-621e4599a861',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:09:24');
INSERT INTO response_analysis VALUES('analysis-mock-2c481b605020','mock-2c481b605020',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:26');
INSERT INTO response_analysis VALUES('analysis-mock-67ddd8d65294','mock-67ddd8d65294',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:26');
INSERT INTO response_analysis VALUES('analysis-mock-c15b0e5b5057','mock-c15b0e5b5057',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:26');
INSERT INTO response_analysis VALUES('analysis-mock-269274be7442','mock-269274be7442',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:26');
INSERT INTO response_analysis VALUES('analysis-mock-fb5d59e45473','mock-fb5d59e45473',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:26');
INSERT INTO response_analysis VALUES('analysis-mock-bdf6d2697d75','mock-bdf6d2697d75',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:26');
INSERT INTO response_analysis VALUES('analysis-mock-3c06a7085f0f','mock-3c06a7085f0f',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:26');
INSERT INTO response_analysis VALUES('analysis-mock-18553edf8e5d','mock-18553edf8e5d',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:57');
INSERT INTO response_analysis VALUES('analysis-mock-03824e2b406b','mock-03824e2b406b',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:57');
INSERT INTO response_analysis VALUES('analysis-mock-d35cf01b2348','mock-d35cf01b2348',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:57');
INSERT INTO response_analysis VALUES('analysis-mock-41a5cd9e507c','mock-41a5cd9e507c',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:57');
INSERT INTO response_analysis VALUES('analysis-mock-aa6a39371a3b','mock-aa6a39371a3b',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:57');
INSERT INTO response_analysis VALUES('analysis-mock-fa848ab698c0','mock-fa848ab698c0',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:10:57');
INSERT INTO response_analysis VALUES('analysis-mock-e1c8ef7926d0','mock-e1c8ef7926d0',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:11:01');
INSERT INTO response_analysis VALUES('analysis-mock-2d8fd315cf9c','mock-2d8fd315cf9c',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:17:32');
INSERT INTO response_analysis VALUES('analysis-mock-eb80c644f28f','mock-eb80c644f28f',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:17:32');
INSERT INTO response_analysis VALUES('analysis-mock-eadb67712881','mock-eadb67712881',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:17:32');
INSERT INTO response_analysis VALUES('analysis-mock-4a0dbbbfb17f','mock-4a0dbbbfb17f',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:17:32');
INSERT INTO response_analysis VALUES('analysis-mock-188341555fe8','mock-188341555fe8',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:17:32');
INSERT INTO response_analysis VALUES('analysis-mock-9ba9591ff128','mock-9ba9591ff128',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:17:32');
INSERT INTO response_analysis VALUES('analysis-mock-1fff03e9eaa4','mock-1fff03e9eaa4',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:17:37');
INSERT INTO response_analysis VALUES('analysis-mock-a14490649e22','mock-a14490649e22',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:23:57');
INSERT INTO response_analysis VALUES('analysis-mock-cf7f8ee9261e','mock-cf7f8ee9261e',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:23:57');
INSERT INTO response_analysis VALUES('analysis-mock-c0d8353d16d7','mock-c0d8353d16d7',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:23:57');
INSERT INTO response_analysis VALUES('analysis-mock-a10bff4ea55f','mock-a10bff4ea55f',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:23:57');
INSERT INTO response_analysis VALUES('analysis-mock-2c334556ca4e','mock-2c334556ca4e',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:23:57');
INSERT INTO response_analysis VALUES('analysis-mock-a4b8fd194742','mock-a4b8fd194742',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:23:57');
INSERT INTO response_analysis VALUES('analysis-mock-6792daf2a5f9','mock-6792daf2a5f9',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:24:01');
INSERT INTO response_analysis VALUES('analysis-mock-8ae78cee18bb','mock-8ae78cee18bb',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:26:39');
INSERT INTO response_analysis VALUES('analysis-mock-86be3e6fb794','mock-86be3e6fb794',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:26:39');
INSERT INTO response_analysis VALUES('analysis-mock-e558dd9b5011','mock-e558dd9b5011',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:26:39');
INSERT INTO response_analysis VALUES('analysis-mock-c58f106cea24','mock-c58f106cea24',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:26:39');
INSERT INTO response_analysis VALUES('analysis-mock-9b00412a3116','mock-9b00412a3116',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:26:39');
INSERT INTO response_analysis VALUES('analysis-mock-4d213c603a74','mock-4d213c603a74',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:26:39');
INSERT INTO response_analysis VALUES('analysis-mock-7c3964419ee7','mock-7c3964419ee7',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:26:44');
INSERT INTO response_analysis VALUES('analysis-mock-54b5dba2d234','mock-54b5dba2d234',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:29:26');
INSERT INTO response_analysis VALUES('analysis-mock-2a72025bc8cc','mock-2a72025bc8cc',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:29:26');
INSERT INTO response_analysis VALUES('analysis-mock-f5cb629b6b3f','mock-f5cb629b6b3f',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:29:26');
INSERT INTO response_analysis VALUES('analysis-mock-be7b4b05e065','mock-be7b4b05e065',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:29:26');
INSERT INTO response_analysis VALUES('analysis-mock-038603e18b96','mock-038603e18b96',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:29:26');
INSERT INTO response_analysis VALUES('analysis-mock-22065b5c0ea7','mock-22065b5c0ea7',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:29:26');
INSERT INTO response_analysis VALUES('analysis-mock-6753a996f787','mock-6753a996f787',0,0,NULL,'[]','[]','[]',0.0,1,'2026-08-17 20:29:31');
CREATE TABLE citations (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    normalized_url TEXT UNIQUE NOT NULL,
    domain TEXT NOT NULL,
    page_title TEXT,
    source_category TEXT,     -- "striim_owned", "competitor", "partner_docs", "review_platform", etc.
    first_observed DATETIME NOT NULL,
    last_observed DATETIME NOT NULL,
    occurrence_count INTEGER DEFAULT 1,
    extraction_metadata TEXT,  -- JSON: {engine, topics}
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE citation_occurrences (
    id TEXT PRIMARY KEY,
    citation_id TEXT NOT NULL,
    response_analysis_id TEXT NOT NULL,
    claim_text TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (citation_id) REFERENCES citations(id),
    FOREIGN KEY (response_analysis_id) REFERENCES response_analysis(id)
);
CREATE TABLE website_checks (
    id TEXT PRIMARY KEY,
    striim_url TEXT NOT NULL,
    crawler TEXT NOT NULL,
    robots_allowed INTEGER,
    in_sitemap INTEGER,
    http_status INTEGER,
    response_time_ms INTEGER,
    noindex INTEGER,
    canonical_url TEXT,
    result TEXT,              -- "publicly_accessible", "blocked_by_robots", "http_error_4xx", etc.
    check_timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE crawler_logs (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    host TEXT NOT NULL,
    path TEXT NOT NULL,
    crawler TEXT,
    http_status INTEGER,
    response_time_ms INTEGER,
    edge_action TEXT,        -- "blocked", "allowed"
    log_source TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE visibility_metrics (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    dimension TEXT NOT NULL, -- "overall", "by_topic", "by_persona", "by_engine"
    dimension_value TEXT,
    striim_mention_rate REAL,
    striim_recommendation_rate REAL,
    striim_top3_rate REAL,
    striim_avg_position REAL,
    striim_citation_rate REAL,
    competitor_mention_rates TEXT,  -- JSON: {Fivetran: 0.58, ...}
    num_responses INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES evaluation_runs(run_id)
);
CREATE TABLE gaps (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    gap_type TEXT NOT NULL,  -- "visibility", "citation", "content", "technical", "authority"
    striim_visibility REAL,
    top_competitor_visibility REAL,
    top_competitor_name TEXT,
    affected_prompts TEXT,   -- JSON: ["oracle-cdc-001", ...]
    evidence_ids TEXT,       -- JSON: ["run-144", "citation-38", ...]
    priority TEXT,           -- "high", "medium", "low"
    confidence TEXT,         -- "high", "medium", "low"
    run_id TEXT NOT NULL,
    created_timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES evaluation_runs(run_id)
);
CREATE TABLE recommendations (
    id TEXT PRIMARY KEY,
    gap_id TEXT NOT NULL,
    problem TEXT NOT NULL,
    evidence_summary TEXT,
    recommended_action TEXT NOT NULL,
    affected_pages TEXT,     -- JSON: ["https://...", ...]
    suggested_owner TEXT,
    priority INTEGER,        -- 1-10
    estimated_effort INTEGER, -- 1-3 (story points)
    measurement_plan TEXT,
    confidence TEXT,         -- "high", "medium", "low"
    status TEXT NOT NULL DEFAULT "draft", -- "draft", "pending_approval", "approved", "rejected", "implemented"
    created_by TEXT,
    approved_by TEXT,
    approval_timestamp DATETIME,
    review_notes TEXT,       -- JSON: {comment, reason}
    created_timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gap_id) REFERENCES gaps(id)
);
CREATE TABLE data_retention_policy (
    table_name TEXT PRIMARY KEY,
    retention_days INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO data_retention_policy VALUES('raw_responses',365,'2026-08-17 19:35:50','2026-08-17 19:35:50');
INSERT INTO data_retention_policy VALUES('response_analysis',365,'2026-08-17 19:35:50','2026-08-17 19:35:50');
INSERT INTO data_retention_policy VALUES('citations',365,'2026-08-17 19:35:50','2026-08-17 19:35:50');
INSERT INTO data_retention_policy VALUES('website_checks',365,'2026-08-17 19:35:50','2026-08-17 19:35:50');
INSERT INTO data_retention_policy VALUES('crawler_logs',90,'2026-08-17 19:35:50','2026-08-17 19:35:50');
INSERT INTO data_retention_policy VALUES('visibility_metrics',NULL,'2026-08-17 19:35:50','2026-08-17 19:35:50');
INSERT INTO data_retention_policy VALUES('gaps',NULL,'2026-08-17 19:35:50','2026-08-17 19:35:50');
INSERT INTO data_retention_policy VALUES('recommendations',NULL,'2026-08-17 19:35:50','2026-08-17 19:35:50');
CREATE TABLE prompts (
    id TEXT PRIMARY KEY,
    prompt_text TEXT NOT NULL,
    topic TEXT,
    persona TEXT,
    intent TEXT,
    priority TEXT,
    enabled INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_evaluation_runs_timestamp ON evaluation_runs(timestamp DESC);
CREATE INDEX idx_evaluation_runs_engine ON evaluation_runs(engine);
CREATE INDEX idx_raw_responses_run_prompt_engine ON raw_responses(run_id, prompt_id, engine);
CREATE INDEX idx_raw_responses_created_at ON raw_responses(created_at DESC);
CREATE INDEX idx_response_analysis_raw_response_id ON response_analysis(raw_response_id);
CREATE INDEX idx_response_analysis_flagged ON response_analysis(flagged_for_review);
CREATE INDEX idx_citations_normalized_url ON citations(normalized_url);
CREATE INDEX idx_citations_domain ON citations(domain);
CREATE INDEX idx_citations_source_category ON citations(source_category);
CREATE INDEX idx_citation_occurrences_citation_id ON citation_occurrences(citation_id);
CREATE INDEX idx_citation_occurrences_analysis_id ON citation_occurrences(response_analysis_id);
CREATE INDEX idx_website_checks_striim_url_crawler ON website_checks(striim_url, crawler);
CREATE INDEX idx_website_checks_check_timestamp ON website_checks(check_timestamp DESC);
CREATE INDEX idx_crawler_logs_timestamp_crawler_host ON crawler_logs(timestamp DESC, crawler, host);
CREATE INDEX idx_crawler_logs_host_path_crawler ON crawler_logs(host, path, crawler);
CREATE INDEX idx_crawler_logs_http_status ON crawler_logs(http_status);
CREATE INDEX idx_visibility_metrics_run_dimension ON visibility_metrics(run_id, dimension);
CREATE INDEX idx_visibility_metrics_dimension_value ON visibility_metrics(dimension_value);
CREATE INDEX idx_gaps_topic_gap_type ON gaps(topic, gap_type);
CREATE INDEX idx_gaps_priority ON gaps(priority);
CREATE INDEX idx_gaps_run_id_created_timestamp ON gaps(run_id, created_timestamp);
CREATE INDEX idx_recommendations_status ON recommendations(status);
CREATE INDEX idx_recommendations_gap_id ON recommendations(gap_id);
CREATE INDEX idx_recommendations_priority_status ON recommendations(priority DESC, status);
CREATE INDEX idx_prompts_topic ON prompts(topic);
COMMIT;
