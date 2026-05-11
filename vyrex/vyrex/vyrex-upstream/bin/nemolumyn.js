#!/usr/bin/env node
// @ts-nocheck
// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
//
// VyrexLumyn — alias for Vyrex with the Lumyn agent pre-selected.
process.env.VYREX_AGENT = "lumyn";
module.exports = require("../dist/vyrex");
