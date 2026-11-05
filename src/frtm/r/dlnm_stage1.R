# Stage 1 DLNM: one model per département x age band (sexes pooled), 2000-2025.
#   log E[deaths] = cb(tm, lag 0-21) + ns(time, 8 df/yr) + dow + holiday + offset(log pop)
#   cb: natural splines, temperature knots at the 10/75/90th percentiles of the département's
#       own distribution, lag knots log-spaced (3 knots). Covid (Mar 2020 - Jun 2021) rows kept
#       in the series (lags need them) but their deaths set to NA so they do not enter the fit.
# Outputs in data/results/dlnm/: curves.csv, lag_curves.csv, summary.csv, stage1_reduced.rds
suppressPackageStartupMessages({
  library(arrow); library(dplyr); library(dlnm); library(splines); library(jsonlite)
})

args   <- commandArgs(trailingOnly = TRUE)
metro  <- c(sprintf("%02d", setdiff(1:95, 20)), "2A", "2B")
pilots <- if (length(args)) args else metro
bands  <- c("0-64", "65-74", "75-84", "85+")
out    <- "data/results/dlnm"
dir.create(out, recursive = TRUE, showWarnings = FALSE)

panel <- open_dataset("data/gold/panel.parquet") |>
  filter(dept %in% pilots, date >= as.Date("1999-12-01"), date <= as.Date("2025-12-31")) |>
  select(date, dept, age_band, deaths, pop, tm, dow, holiday) |>
  collect() |>
  group_by(date, dept, age_band) |>
  summarise(deaths = sum(deaths), pop = sum(pop), tm = first(tm), dow = first(dow),
            holiday = first(holiday), .groups = "drop") |>
  arrange(dept, age_band, date)

fit_one <- function(d) {
  covid <- d$date >= as.Date("2020-03-01") & d$date <= as.Date("2021-06-30")
  d$deaths_fit <- d$deaths; d$deaths_fit[covid] <- NA
  d$time <- as.numeric(d$date - min(d$date))
  nyears <- as.numeric(diff(range(d$date))) / 365.25
  qs <- quantile(d$tm, c(.10, .75, .90), na.rm = TRUE)
  cb <- crossbasis(d$tm, lag = 21,
                   argvar = list(fun = "ns", knots = qs),
                   arglag = list(fun = "ns", knots = logknots(21, 3)))
  m <- glm(deaths_fit ~ cb + ns(time, df = round(8 * nyears)) + factor(dow) + holiday + offset(log(pop)),
           family = quasipoisson(), data = d)
  rng <- quantile(d$tm, c(.01, .99), na.rm = TRUE)
  pr0 <- crosspred(cb, m, cen = median(d$tm, na.rm = TRUE), by = 0.1)
  ok  <- pr0$predvar >= rng[1] & pr0$predvar <= rng[2]
  mmt <- pr0$predvar[ok][which.min(pr0$allRRfit[ok])]          # minimum-mortality temperature
  pr  <- crosspred(cb, m, cen = mmt, by = 0.1)
  red <- crossreduce(cb, m, cen = mmt)                             # overall cumulative, for stage 2
  at  <- function(x) which.min(abs(pr$predvar - x))
  list(mmt = mmt, mmt_pct = mean(d$tm <= mmt, na.rm = TRUE), p1 = rng[[1]], p99 = rng[[2]],
       rr_p1 = pr$allRRfit[at(rng[1])], rr_p99 = pr$allRRfit[at(rng[2])],
       rr_p99_lo = pr$allRRlow[at(rng[2])], rr_p99_hi = pr$allRRhigh[at(rng[2])],
       phi = summary(m)$dispersion, n_days = sum(!is.na(d$deaths_fit)),
       curve = data.frame(tm = pr$predvar, rr = pr$allRRfit, lo = pr$allRRlow, hi = pr$allRRhigh),
       lag_heat = data.frame(lag = 0:21, rr = pr$matRRfit[at(rng[2]), ], lo = pr$matRRlow[at(rng[2]), ], hi = pr$matRRhigh[at(rng[2]), ]),
       lag_cold = data.frame(lag = 0:21, rr = pr$matRRfit[at(rng[1]), ], lo = pr$matRRlow[at(rng[1]), ], hi = pr$matRRhigh[at(rng[1]), ]),
       coef = coef(red), vcov = vcov(red),
       tm_knots = qs, tm_range = range(d$tm, na.rm = TRUE), tm_q = quantile(d$tm, seq(0, 1, 0.01), na.rm = TRUE))
}

curves <- list(); lags <- list(); summ <- list(); reduced <- list()
jobs <- expand.grid(dept = pilots, band = bands, stringsAsFactors = FALSE)
fit_job <- function(i) {
  dp <- jobs$dept[i]; b <- jobs$band[i]
  d <- panel |> filter(dept == dp, age_band == b)
  r <- tryCatch(fit_one(as.data.frame(d)), error = function(e) { message(dp, " ", b, " failed: ", conditionMessage(e)); NULL })
  if (!is.null(r)) cat(sprintf("done %s %-5s mmt=%.1f rr99=%.2f\n", dp, b, r$mmt, r$rr_p99))
  list(dept = dp, band = b, r = r)
}
results <- parallel::mclapply(seq_len(nrow(jobs)), fit_job, mc.cores = 4)
for (res in results) {
  if (is.null(res$r)) next
  dp <- res$dept; b <- res$band; r <- res$r; key <- paste(dp, b, sep = "|")
  curves[[key]] <- cbind(dept = dp, age_band = b, r$curve)
  lags[[key]]   <- rbind(cbind(dept = dp, age_band = b, side = "heat_p99", r$lag_heat),
                         cbind(dept = dp, age_band = b, side = "cold_p1",  r$lag_cold))
  summ[[key]]   <- data.frame(dept = dp, age_band = b, mmt = r$mmt, mmt_pct = r$mmt_pct, p1 = r$p1, p99 = r$p99,
                              rr_p1 = r$rr_p1, rr_p99 = r$rr_p99, rr_p99_lo = r$rr_p99_lo, rr_p99_hi = r$rr_p99_hi,
                              phi = r$phi, n_days = r$n_days)
  reduced[[key]] <- list(dept = dp, age_band = b, mmt = r$mmt, coef = r$coef, vcov = r$vcov,
                         tm_knots = r$tm_knots, tm_range = r$tm_range, tm_q = r$tm_q)
}

write.csv(do.call(rbind, curves), file.path(out, "curves.csv"), row.names = FALSE)
write.csv(do.call(rbind, lags),   file.path(out, "lag_curves.csv"), row.names = FALSE)
write.csv(do.call(rbind, summ),   file.path(out, "summary.csv"), row.names = FALSE)
saveRDS(reduced, file.path(out, "stage1_reduced.rds"))
print(do.call(rbind, summ), digits = 3)