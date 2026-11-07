function ofdm_reference(folder, doppler_hz, sample_rate, delay)
  % MATLAB-compatible code, executed using free GNU Octave in CI.
  tx = dlmread(fullfile(folder, 'tx.csv'), ',');
  samples = tx(:,1) + 1i*tx(:,2);
  n = (0:length(samples)-1)';
  impaired = [zeros(delay,1); samples .* exp(2i*pi*doppler_hz*n/sample_rate)];
  aligned = impaired(delay+1:delay+length(samples));
  corrected = aligned .* exp(-2i*pi*doppler_hz*n/sample_rate);
  frames = reshape(corrected,80,[]);
  frequency = fft(frames(17:80,:),64,1)/8;
  result = frequency(:);
  dlmwrite(fullfile(folder,'rx.csv'),[real(result),imag(result)],',','precision','%.16g');
end
