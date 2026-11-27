"""Empirical error simulation becomes available only after real observations."""
import random
import statistics

def error_summary(errors,predicted_seconds,minimum=10):
    result={'n':len(errors),'minimum':minimum,'mae_seconds':None,'simulated_interval_seconds':None}
    if len(errors)<minimum:return result
    rng=random.Random(8840)
    simulations=sorted(max(0,predicted_seconds+rng.choice(errors)) for _ in range(1000))
    result.update(mae_seconds=round(statistics.mean(abs(x) for x in errors)),
                  mean_error_seconds=round(statistics.mean(errors)),
                  simulated_interval_seconds=[round(simulations[100]),round(simulations[899])],
                  method='같은 경로 조건의 실측 오차를 재표집한 80% 시나리오 구간 · 보장 구간 아님')
    return result
