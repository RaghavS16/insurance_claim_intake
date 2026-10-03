import {describe,expect,it} from 'vitest';
import {render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import Shell from '../components/Shell';

describe('accessibility smoke',()=>{
  it('provides labelled navigation and meaningful controls',()=>{
    render(<MemoryRouter><Shell user={{role:'CLAIMANT',full_name:'Claimant'}}/></MemoryRouter>);
    expect(screen.getByRole('navigation')).toBeInTheDocument();
    expect(screen.getAllByRole('link').length).toBeGreaterThan(0);
    for(const button of screen.queryAllByRole('button')){
      expect(button).toHaveAccessibleName();
    }
  });
});